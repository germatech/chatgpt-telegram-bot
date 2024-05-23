from __future__ import annotations

import asyncio
import itertools
import json
import os
import re
import base64
import logging

import telegram
from telegram import (
    Message,
    MessageEntity,
    Update,
    ChatMember,
    constants,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import CallbackContext, ContextTypes

from cryptomus_client import CryptomusManager
from ains_client import RedeemManager
from tlync_client import TlyncClient, DataBody
from usage import UsageTracker
from config import chat_modes, BotConfig, plans


def message_text(message: Message) -> str:
    """
    Returns the text of a message, excluding any bot commands.
    """
    message_txt = message.text
    if message_txt is None:
        return ""

    for _, text in sorted(
            message.parse_entities([MessageEntity.BOT_COMMAND]).items(),
            key=(lambda item: item[0].offset),
    ):
        message_txt = message_txt.replace(text, "").strip()

    return message_txt if len(message_txt) > 0 else ""


async def is_user_in_group(
        update: Update, context: CallbackContext, user_id: int
) -> bool:
    """
    Checks if user_id is a member of the group
    """
    try:
        chat_member = await context.bot.get_chat_member(update.message.chat_id, user_id)
        return chat_member.status in [
            ChatMember.OWNER,
            ChatMember.ADMINISTRATOR,
            ChatMember.MEMBER,
        ]
    except telegram.error.BadRequest as e:
        if str(e) == "User not found":
            return False
        else:
            raise e
    except Exception as e:
        raise e


def get_thread_id(update: Update) -> int | None:
    """
    Gets the message thread id for the update, if any
    """
    if update.effective_message and update.effective_message.is_topic_message:
        return update.effective_message.message_thread_id
    return None


def get_stream_cutoff_values(update: Update, content: str) -> int:
    """
    Gets the stream cutoff values for the message length
    """
    if is_group_chat(update):
        # group chats have stricter flood limits
        return (
            180
            if len(content) > 1000
            else 120 if len(content) > 200 else 90 if len(content) > 50 else 50
        )
    return (
        90
        if len(content) > 1000
        else 45 if len(content) > 200 else 25 if len(content) > 50 else 15
    )


def is_group_chat(update: Update) -> bool:
    """
    Checks if the message was sent from a group chat
    """
    if not update.effective_chat:
        return False
    return update.effective_chat.type in [
        constants.ChatType.GROUP,
        constants.ChatType.SUPERGROUP,
    ]


def split_into_chunks(text: str, chunk_size: int = 4096) -> list[str]:
    """
    Splits a string into chunks of a given size.
    """
    return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)]


async def wrap_with_indicator(
        update: Update,
        context: CallbackContext,
        coroutine,
        chat_action: constants.ChatAction = "",
        is_inline=False,
):
    """
    Wraps a coroutine while repeatedly sending a chat action to the user.
    """
    task = context.application.create_task(coroutine(), update=update)
    while not task.done():
        if not is_inline:
            context.application.create_task(
                update.effective_chat.send_action(
                    chat_action, message_thread_id=get_thread_id(update)
                )
            )
        try:
            await asyncio.wait_for(asyncio.shield(task), 4.5)
        except asyncio.TimeoutError:
            pass


async def edit_message_with_retry(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int | None,
        message_id: str,
        text: str,
        markdown: bool = True,
        is_inline: bool = False,
):
    """
    Edit a message with retry logic in case of failure (e.g. broken markdown)
    :param context: The context to use
    :param chat_id: The chat id to edit the message in
    :param message_id: The message id to edit
    :param text: The text to edit the message with
    :param markdown: Whether to use markdown parse mode
    :param is_inline: Whether the message to edit is an inline message
    :return: None
    """
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=int(message_id) if not is_inline else None,
            inline_message_id=message_id if is_inline else None,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN if markdown else None,
        )
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            return
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(message_id) if not is_inline else None,
                inline_message_id=message_id if is_inline else None,
                text=text,
            )
        except Exception as e:
            logging.warning(f"Failed to edit message: {str(e)}")
            raise e

    except Exception as e:
        logging.warning(str(e))
        raise e


async def error_handler(_: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles errors in the telegram-python-bot library.
    """
    logging.error(f"Exception while handling an update: {context.error}")


async def is_allowed(
        config: BotConfig, update: Update, context: CallbackContext, is_inline=False
) -> bool:
    """
    Checks if the user is allowed to use the bot.
    """
    if config.allowed_user_ids == "*":
        return True

    user_id = (
        update.inline_query.from_user.id if is_inline else update.message.from_user.id
    )
    if is_admin(config, user_id):
        return True
    name = (
        update.inline_query.from_user.name
        if is_inline
        else update.message.from_user.name
    )
    allowed_user_ids = config.allowed_user_ids.split(",")
    # Check if user is allowed
    if str(user_id) in allowed_user_ids:
        return True
    # Check if it's a group a chat with at least one authorized member
    if not is_inline and is_group_chat(update):
        admin_user_ids = config.admin_user_ids.split(",")
        for user in itertools.chain(allowed_user_ids, admin_user_ids):
            if not user.strip():
                continue
            if await is_user_in_group(update, context, user):
                logging.info(f"{user} is a member. Allowing group chat message...")
                return True
        logging.info(
            f"Group chat messages from user {name} " f"(id: {user_id}) are not allowed"
        )
    return False


def is_admin(config: BotConfig, user_id: int, log_no_admin=False) -> bool:
    """
    Checks if the user is the admin of the bot.
    The first user in the user list is the admin.
    """
    if config.admin_user_ids == "-":
        if log_no_admin:
            logging.info("No admin user defined.")
        return False

    admin_user_ids = config.admin_user_ids.split(",")

    # Check if user is in the admin user list
    if str(user_id) in admin_user_ids:
        return True

    return False


def get_user_budget(config: BotConfig, user_id) -> float | None:
    """
    Get the user's budget based on their user ID and the bot configuration.
    :param config: The bot configuration object
    :param user_id: User id
    :return: The user's budget as a float, or None if the user is not found in the allowed user list
    """

    # no budget restrictions for admins and '*'-budget lists
    if is_admin(config, user_id):
        return float("inf")

    user_budgets = config.user_budgets.split(",")
    logging.info(f"user budgets {user_budgets}")
    if config.allowed_user_ids == "*":
        # same budget for all users, use value in first position of budget list
        if len(user_budgets) > 1:
            logging.warning(
                "multiple values for budgets set with unrestricted user list "
                "only the first value is used as budget for everyone."
            )
        return float(user_budgets[0])

    allowed_user_ids = config.allowed_user_ids.split(",")
    if str(user_id) in allowed_user_ids:
        user_index = allowed_user_ids.index(str(user_id))
        if len(user_budgets) <= user_index:
            logging.warning(
                f"No budget set for user id: {user_id}. Budget list shorter than user list."
            )
            return 0.0
        return float(user_budgets[user_index])
    return None


async def get_remaining_budget(
        config: BotConfig, usage, update: Update, is_inline=False
) -> float:
    """
    Calculate the remaining budget for a user based on their current usage.
    :param config: The bot configuration object
    :param usage: The usage tracker object
    :param update: Telegram update object
    :param is_inline: Boolean flag for inline queries
    :return: The remaining budget for the user as a float
    """
    # Mapping of budget period to cost period

    budget_cost_map = {
        "monthly": "cost_month",
        "daily": "cost_today",
        "all-time": "cost_all_time",
    }

    user_id = (
        update.inline_query.from_user.id if is_inline else update.message.from_user.id
    )
    name = (
        update.inline_query.from_user.name
        if is_inline
        else update.message.from_user.name
    )
    if user_id not in usage:
        usage[user_id] = UsageTracker.create(user_id, name)

    if is_admin(config, user_id):
        return float("inf")

    # Get budget for users
    # user_budget = get_user_budget(config, user_id)
    user_budget = usage[user_id].get_the_total_user_budget(status="active")
    if user_budget["total_payment"] <= 0:
        raise ValueError("no budget to use the bot")
    budget_period = config.budget_period
    if user_budget is not None:
        cost = usage[user_id].get_current_cost()[budget_cost_map[budget_period]]
        logging.info(f"the cost is {cost}")
        return user_budget["total_payment"] - cost

    # Get budget for guests
    if "guests" not in usage:
        usage["guests"] = UsageTracker.create(
            "guests", "all guest users in group chats"
        )
    cost = usage["guests"].get_current_cost()[budget_cost_map[budget_period]]
    return config.guest_budget - cost


async def is_within_budget(
        config: BotConfig, usage, update: Update, is_inline=False
) -> bool:
    """
    Checks if the user reached their usage limit.
    Initializes UsageTracker for user and guest when needed.
    :param config: The bot configuration object
    :param usage: The usage tracker object
    :param update: Telegram update object
    :param is_inline: Boolean flag for inline queries
    :return: Boolean indicating if the user has a positive budget
    """
    user_id = (
        update.inline_query.from_user.id if is_inline else update.message.from_user.id
    )
    name = (
        update.inline_query.from_user.name
        if is_inline
        else update.message.from_user.name
    )
    if user_id not in usage:
        usage[user_id] = UsageTracker.create(user_id, name)
    remaining_budget = await get_remaining_budget(
        config, usage, update, is_inline=is_inline
    )
    logging.info(f"is_within_budget {remaining_budget} and {remaining_budget > 0}")
    return remaining_budget > 0


async def add_chat_request_to_usage_tracker(
        usage, config: BotConfig, user_id, used_tokens
):
    """
    Add chat request to usage tracker
    :param usage: The usage tracker object
    :param config: The bot configuration object
    :param user_id: The user id
    :param used_tokens: The number of tokens used
    """
    try:
        if int(used_tokens) == 0:
            logging.warning("No tokens used. Not adding chat request to usage tracker.")
            return
        # add chat request to users usage tracker
        usage[user_id].add_chat_tokens(used_tokens, config.token_price)
        # add guest chat request to guest usage tracker
        allowed_user_ids = config.allowed_user_ids.split(",")
        if str(user_id) not in allowed_user_ids and "guests" in usage:
            usage["guests"].add_chat_tokens(used_tokens, config.token_price)
    except Exception as e:
        logging.warning(f"Failed to add tokens to usage_logs: {str(e)}")
        pass


def get_reply_to_message_id(config: BotConfig, update: Update):
    """
    Returns the message id of the message to reply to
    :param config: Bot configuration object
    :param update: Telegram update object
    :return: Message id of the message to reply to, or None if quoting is disabled
    """
    if config.enable_quoting or is_group_chat(update):
        return update.message.message_id
    return None


def is_direct_result(response: any) -> bool:
    """
    Checks if the dict contains a direct result that can be sent directly to the user
    :param response: The response value
    :return: Boolean indicating if the result is a direct result
    """
    if type(response) is not dict:
        try:
            json_response = json.loads(response)
            return json_response.get("direct_result", False)
        except:
            return False
    else:
        return response.get("direct_result", False)


async def handle_direct_result(config: BotConfig, update: Update, response: any):
    """
    Handles a direct result from a plugin
    """
    if type(response) is not dict:
        response = json.loads(response)

    result = response["direct_result"]
    kind = result["kind"]
    format = result["format"]
    value = result["value"]

    common_args = {
        "message_thread_id": get_thread_id(update),
        "reply_to_message_id": get_reply_to_message_id(config, update),
    }

    if kind == "photo":
        if format == "url":
            await update.effective_message.reply_photo(**common_args, photo=value)
        elif format == "path":
            await update.effective_message.reply_photo(
                **common_args, photo=open(value, "rb")
            )
    elif kind == "gif" or kind == "file":
        if format == "url":
            await update.effective_message.reply_document(**common_args, document=value)
        if format == "path":
            await update.effective_message.reply_document(
                **common_args, document=open(value, "rb")
            )
    elif kind == "dice":
        await update.effective_message.reply_dice(**common_args, emoji=value)

    if format == "path":
        cleanup_intermediate_files(response)


def cleanup_intermediate_files(response: any):
    """
    Deletes intermediate files created by plugins
    """
    if type(response) is not dict:
        response = json.loads(response)

    result = response["direct_result"]
    format = result["format"]
    value = result["value"]

    if format == "path":
        if os.path.exists(value):
            os.remove(value)


# Function to encode the image
def encode_image(fileobj):
    image = base64.b64encode(fileobj.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{image}"


def decode_image(imgbase64):
    image = imgbase64[len("data:image/jpeg;base64,"):]
    return base64.b64decode(image)


# Function to generate paginated keyboard
def get_paginated_keyboard(page_index):
    n_chat_modes_per_page = 4
    text = f"Select <b>chat mode</b> ({len(chat_modes)} modes available):"
    chat_mode_keys = list(chat_modes.keys())
    if chat_mode_keys:
        page_chat_mode_keys = chat_mode_keys[
                              page_index
                              * n_chat_modes_per_page: (page_index + 1)
                                                       * n_chat_modes_per_page
                              ]

        keyboard = []
        for chat_mode_key in page_chat_mode_keys:
            name = chat_modes[chat_mode_key]["name"]

            keyboard.append(
                [
                    InlineKeyboardButton(
                        name, callback_data=f"set_chat_mode|{chat_mode_key}"
                    )
                ]
            )

        # pagination
        if len(chat_mode_keys) > n_chat_modes_per_page:
            is_first_page = page_index == 0
            is_last_page = (page_index + 1) * n_chat_modes_per_page >= len(
                chat_mode_keys
            )

            if is_first_page:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "»", callback_data=f"show_chat_modes|{page_index + 1}"
                        )
                    ]
                )
            elif is_last_page:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "«", callback_data=f"show_chat_modes|{page_index - 1}"
                        ),
                    ]
                )
            else:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "«", callback_data=f"show_chat_modes|{page_index - 1}"
                        ),
                        InlineKeyboardButton(
                            "»", callback_data=f"show_chat_modes|{page_index + 1}"
                        ),
                    ]
                )

        reply_markup = InlineKeyboardMarkup(keyboard)
        logging.info(f"replay markup from utils {reply_markup}")
        logging.info(f"text from utils {text}")
        return text, reply_markup
    else:
        raise ValueError("chat modes list is empty or None")


async def get_payments_buttons():
    text = "Buy Now"
    buttons = []

    for model_key in plans["methods"]:
        button_text = model_key
        buttons.append(
            InlineKeyboardButton(button_text, callback_data=f"payments|{model_key}")
        )

    # Divide buttons into rows of 3 buttons each
    button_rows = [buttons[i: i + 3] for i in range(0, len(buttons), 3)]

    reply_markup = InlineKeyboardMarkup(button_rows)
    return text, reply_markup


def replace_placeholders(obj, replacements):
    if isinstance(obj, dict):
        for key, value in obj.items():
            obj[key] = replace_placeholders(value, replacements)
    elif isinstance(obj, list):
        obj = [replace_placeholders(item, replacements) for item in obj]
    elif isinstance(obj, str):
        for placeholder, actual_value in replacements.items():
            obj = obj.replace(placeholder, str(actual_value))
    return obj


def extract_user_id(s):
    match = re.search(r"-(\d+)-", s)
    return match.group(1) if match else None


def payment_switcher(
        user_payment_choice: str,
        user_id: int | None = None,
        user_name: str | None = None,
        payment_plan: str | None = None,
        redeem_card: str | None = None,
        config: BotConfig | None = None,
        data: DataBody | None = None,
):
    match user_payment_choice:
        case "crypto":
            return cryptomus_invoice(
                user_id=user_id, user_name=user_name, payment_plan=payment_plan
            )
        case "anis-usdt":
            if redeem_card:
                return anis_redeem(redeem_code=redeem_card, user_id=user_id)
            else:
                raise ValueError("the redeem card is missing")
        case "donation":
            return "Sorry it's not available at the moment"
        case "local-lyd":
            return local_payment(config=config, data=data)


def cryptomus_invoice(user_id: int, user_name: str, payment_plan: str):
    crypto = CryptomusManager()
    try:
        logging.debug("Cryptomus Activated ...")
        url, order_id = crypto.create_invoice(
            user_id=user_id, user_name=user_name, payment_method=payment_plan
        )
        return url, order_id
    except Exception as e:
        logging.error(f"An error with cryptomus method for some reason: {e}")
        raise


def anis_redeem(redeem_code: str, user_id: int):
    anis = RedeemManager()
    try:
        resp = anis.anis_redeem_code(redeem_code=redeem_code, user_id=user_id)
        if resp["coin"] != "USDT":
            coin = resp["coin"]
            amount = resp["amount"]
            coin_price = anis.exchange_price(coin=f"{coin}USDT")
            resp["coin"] = "USDT"
            resp["amount"] = amount * coin_price
        return None, resp
    except Exception as e:
        logging.error(f"An error with binance redeem method for some reason: {e}")
        raise


def local_payment(config: BotConfig, data: DataBody):
    lync_api = TlyncClient(is_test_environment=True)
    lync_api.set_token(config.tlync_token)
    try:
        resp = lync_api.initiate_payment(data=data)
        logging.info(f"the reponse is {resp}")
        return resp
    except Exception as e:
        logging.error(f"there is error happened {e}")


def clean_string(data):
    data = data.lower()
    data = re.sub(r"[ /]", "-", data)
    emoj = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002500-\U00002BEF"  # chinese char
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937"
        "\U00010000-\U0010ffff"
        "\u2640-\u2642"
        "\u2600-\u2B55"
        "\u200d"
        "\u23cf"
        "\u23e9"
        "\u231a"
        "\ufe0f"  # dingbats
        "\u3030"
        "]+",
        re.UNICODE,
    )
    return re.sub(emoj, "", data)


def get_plan_image(subs_plan: str, config: BotConfig):
    image = {
        "crypto": config.crypto_image_path,
        "libyan-payments": config.libyan_image_path,
        "anis-usdt": config.anis_image_path,
        "donation": config.donation_image_path,
    }

    return image[subs_plan] if subs_plan else None
