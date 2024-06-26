import asyncio
import re
import logging
import os
import io
import time

from uuid import uuid4
from telegram import BotCommandScopeAllGroupChats, Update, constants
from telegram import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultArticle,
)
from telegram import InputTextMessageContent, BotCommand
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TimedOut, BadRequest
from telegram.ext import (
    Application,
    ContextTypes,
    CallbackContext,
    ConversationHandler,
)

from pydub import AudioSegment
from PIL import Image

from utils import (
    is_group_chat,
    get_thread_id,
    message_text,
    wrap_with_indicator,
    split_into_chunks,
    edit_message_with_retry,
    get_stream_cutoff_values,
    is_allowed,
    get_remaining_budget,
    is_within_budget,
    get_reply_to_message_id,
    add_chat_request_to_usage_tracker,
    is_direct_result,
    handle_direct_result,
    cleanup_intermediate_files,
    get_paginated_keyboard,
    get_payments_buttons,
    clean_string,
    get_plan_image,
    payment_switcher
)
from openai_helper import OpenAIHelper, localized_text
from usage import UsageTracker
from config import chat_modes, BotConfig, plans
from tlync_client import DataBody


class ChatGPTTelegramBot:
    """
    Class representing a ChatGPT Telegram Bot.
    """

    def __init__(self, config: BotConfig, openai: OpenAIHelper):
        """
        Initializes the bot with the given configuration and GPT bot object.
        :param config: A dictionary containing the bot configuration
        :param openai: OpenAIHelper object
        """
        self.config = config
        self.openai = openai
        bot_language = self.config.bot_language
        self.REDEEM_CODE = 0
        self.commands = [
            BotCommand(
                command="reset",
                description=localized_text("help_commands", bot_language)[0],
            ),
            BotCommand(
                command="brains",
                description=localized_text("help_commands", bot_language)[2],
            ),
            BotCommand(
                command="payments",
                description=localized_text("help_commands", bot_language)[1],
            ),
            BotCommand(
                command="stats",
                description=localized_text("stats_description", bot_language),
            ),
            BotCommand(
                command="resend",
                description=localized_text("resend_description", bot_language),
            ),
            BotCommand(
                command="help",
                description=localized_text("help_commands", bot_language)[5],
            ),
            BotCommand(
                command="cancel",
                description="إلغاء العملية 🚫",
            )
        ]
        # If imaging is enabled, add the "image" command to the list
        if self.config.enable_image_generation:
            self.commands.append(
                BotCommand(
                    command="image",
                    description=localized_text("image_description", bot_language),
                )
            )

        if self.config.enable_tts_generation:
            self.commands.append(
                BotCommand(
                    command="tts",
                    description=localized_text("tts_description", bot_language),
                )
            )

        self.group_commands = [
                                  BotCommand(
                                      command="chat",
                                      description=localized_text("chat_description", bot_language),
                                  )
                              ] + self.commands
        self.disallowed_message = localized_text("disallowed", bot_language)
        self.budget_limit_message = localized_text("budget_limit", bot_language)
        self.usage = {}
        self.last_message = {}
        self.inline_queries_cache = {}

    async def start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Shows the start menu.
        """
        bot_language = self.config.bot_language

        start_text = (
                localized_text("start_description", bot_language)[0]
                + "\n\n"
                + localized_text("start_description", bot_language)[1]
                + "\n\n"
                + localized_text("start_how_to_use_me", bot_language)[0]
                + "\n"
                + localized_text("start_how_to_use_me", bot_language)[1]
                + "\n"
                + localized_text("start_how_to_use_me", bot_language)[2]
                + "\n"
                + localized_text("start_how_to_use_me", bot_language)[3]
                + "\n"
                + localized_text("start_how_to_use_me", bot_language)[4]
                + "\n\n"
                + localized_text("start_privacy", bot_language)[0]
                + "\n"
                + localized_text("start_privacy", bot_language)[1]
                + "\n\n"
                + localized_text("start_lets_start", bot_language)[0]
                + "\n"
                + localized_text("start_lets_start", bot_language)[1]
        )
        await update.message.reply_text(start_text, disable_web_page_preview=True)

    async def help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Shows the help menu.
        """
        bot_language = self.config.bot_language
        more_info = localized_text("more_info", bot_language)
        commands = self.group_commands if is_group_chat(update) else self.commands
        commands_description = [
            f"/{command.command} - {command.description}" for command in commands
        ]
        help_text = (
                localized_text("help_text", bot_language)[0]
                + "\n\n"
                + "\n".join(commands_description)
                + "\n\n"
                + localized_text("help_text", bot_language)[1]
                + "\n\n"
                + "\n".join(info for info in more_info)
        )
        await update.message.reply_text(help_text, disable_web_page_preview=True)

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Returns token usage statistics for current day and month.
        """
        if not await is_allowed(self.config, update, context):
            logging.warning(
                f"User {update.message.from_user.name} (id: {update.message.from_user.id}) "
                f"is not allowed to request their usage statistics"
            )
            await self.send_disallowed_message(update, context)
            return

        logging.info(
            f"User {update.message.from_user.name} (id: {update.message.from_user.id}) "
            f"requested their usage statistics"
        )

        user_id = update.message.from_user.id
        if user_id not in self.usage:
            self.usage[user_id] = UsageTracker.create(
                user_id, update.message.from_user.name
            )

        tokens_today, tokens_month = self.usage[user_id].get_current_token_usage()
        images_today, images_month = self.usage[user_id].get_current_image_count()
        (
            transcribe_minutes_today,
            transcribe_seconds_today,
            transcribe_minutes_month,
            transcribe_seconds_month,
        ) = self.usage[user_id].get_current_transcription_duration()
        vision_today, vision_month = self.usage[user_id].get_current_vision_tokens()
        characters_today, characters_month = self.usage[user_id].get_current_tts_usage()
        current_cost = self.usage[user_id].get_current_cost()

        chat_id = update.effective_chat.id
        chat_messages, chat_token_length = self.openai.get_conversation_stats(chat_id)
        remaining_budget = await get_remaining_budget(self.config, self.usage, update)
        bot_language = self.config.bot_language

        text_current_conversation = (
            f"*{localized_text('stats_conversation', bot_language)[0]}*:\n"
            f"{chat_messages} {localized_text('stats_conversation', bot_language)[1]}\n"
            f"{chat_token_length} {localized_text('stats_conversation', bot_language)[2]}\n"
            f"----------------------------\n"
        )

        # Check if image generation is enabled and, if so, generate the image statistics for today
        text_today_images = ""
        if self.config.enable_image_generation:
            text_today_images = (
                f"{images_today} {localized_text('stats_images', bot_language)}\n"
            )

        text_today_vision = ""
        if self.config.enable_vision:
            text_today_vision = (
                f"{vision_today} {localized_text('stats_vision', bot_language)}\n"
            )

        text_today_tts = ""
        if self.config.enable_tts_generation:
            text_today_tts = (
                f"{characters_today} {localized_text('stats_tts', bot_language)}\n"
            )

        text_today = (
            f"*{localized_text('usage_today', bot_language)}:*\n"
            f"{tokens_today} {localized_text('stats_tokens', bot_language)}\n"
            f"{text_today_images}"  # Include the image statistics for today if applicable
            f"{text_today_vision}"
            f"{text_today_tts}"
            f"{transcribe_minutes_today} {localized_text('stats_transcribe', bot_language)[0]} "
            f"{transcribe_seconds_today} {localized_text('stats_transcribe', bot_language)[1]}\n"
            f"{localized_text('stats_total', bot_language)}{current_cost['cost_today']:.2f}\n"
            f"----------------------------\n"
        )

        text_month_images = ""
        if self.config.enable_image_generation:
            text_month_images = (
                f"{images_month} {localized_text('stats_images', bot_language)}\n"
            )

        text_month_vision = ""
        if self.config.enable_vision:
            text_month_vision = (
                f"{vision_month} {localized_text('stats_vision', bot_language)}\n"
            )

        text_month_tts = ""
        if self.config.enable_tts_generation:
            text_month_tts = (
                f"{characters_month} {localized_text('stats_tts', bot_language)}\n"
            )

        # Check if image generation is enabled and, if so, generate the image statistics for the month
        text_month = (
            f"*{localized_text('usage_month', bot_language)}:*\n"
            f"{tokens_month} {localized_text('stats_tokens', bot_language)}\n"
            f"{text_month_images}"  # Include the image statistics for the month if applicable
            f"{text_month_vision}"
            f"{text_month_tts}"
            f"{transcribe_minutes_month} {localized_text('stats_transcribe', bot_language)[0]} "
            f"{transcribe_seconds_month} {localized_text('stats_transcribe', bot_language)[1]}\n"
            f"{localized_text('stats_total', bot_language)}{current_cost['cost_month']:.2f}"
        )

        # text_budget filled with conditional content
        text_budget = "\n\n"
        budget_period = self.config.budget_period
        if remaining_budget < float("inf"):
            text_budget += (
                f"{localized_text('stats_budget', bot_language)}"
                f"{localized_text(budget_period, bot_language)}: "
                f"${remaining_budget:.2f}.\n"
            )
        # No longer works as of July 21st 2023, as OpenAI has removed the billing API
        # add OpenAI account information for admin request
        # if is_admin(self.config, user_id):
        #     text_budget += (
        #         f"{localized_text('stats_openai', bot_language)}"
        #         f"{self.openai.get_billing_current_month():.2f}"
        #     )

        usage_text = text_current_conversation + text_today + text_month + text_budget
        await update.message.reply_text(
            usage_text, parse_mode=constants.ParseMode.MARKDOWN
        )

    async def get_chat_modes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        displays a paginated
        keyboard that allows the user to select a chat mode.
        """
        if not await self.check_allowed_and_within_budget(update, context):
            return
        text, reply_markup = get_paginated_keyboard(0)
        await update.message.reply_text(
            "Select <b>chat mode</b>:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )

    async def get_chat_modes_callback(
            self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        processes the callback query, logs relevant information, and updates
        the message with a new set of chat mode options based
        on the page index from the callback data.
        """
        if not await is_allowed(self.config, update, context):
            logging.warning(
                f"User {update.message.from_user.name} (id: {update.message.from_user.id}) "
                f"is not allowed to reset the conversation"
            )
            await self.send_disallowed_message(update, context)
            return
        query = update.callback_query
        await query.answer()

        # Extracting page index from callback data
        page_index = int(query.data.split("|")[1])
        logging.info(f"page index is {page_index}")
        if page_index < 0:
            return

        # Assume user's language is English for simplicity
        text, reply_markup = get_paginated_keyboard(page_index=page_index)

        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )

    async def set_chat_mode_handle(
            self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if not await is_allowed(self.config, update, context):
            logging.warning(
                f"User {update.message.from_user.name} (id: {update.message.from_user.id}) "
                f"is not allowed to reset the conversation"
            )
            await self.send_disallowed_message(update, context)
            return

        user_id = update.callback_query.from_user.id
        chat_id = update.effective_chat.id
        query = update.callback_query
        await query.answer()

        chat_mode = query.data.split("|")[1]
        core_chat_mode = chat_modes
        self.usage[user_id].update_user_brain(chat_mode)
        brain_prompt = core_chat_mode[chat_mode]["prompt_start"]
        self.openai.reset_chat_history(chat_id=chat_id, content=brain_prompt)
        await context.bot.send_message(
            update.callback_query.message.chat.id,
            f"{core_chat_mode[chat_mode]['welcome_message']}",
            parse_mode=ParseMode.HTML,
        )

    async def resend(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Resend the last request
        """
        if not await is_allowed(self.config, update, context):
            logging.warning(
                f"User {update.message.from_user.name}  (id: {update.message.from_user.id})"
                f" is not allowed to resend the message"
            )
            await self.send_disallowed_message(update, context)
            return

        chat_id = update.effective_chat.id
        if chat_id not in self.last_message:
            logging.warning(
                f"User {update.message.from_user.name} (id: {update.message.from_user.id})"
                f" does not have anything to resend"
            )
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=localized_text("resend_failed", self.config.bot_language),
            )
            return

        # Update message text, clear self.last_message and send the request to prompt
        logging.info(
            f"Resending the last prompt from user: {update.message.from_user.name} "
            f"(id: {update.message.from_user.id})"
        )
        with update.message._unfrozen() as message:
            message.text = self.last_message.pop(chat_id)

        await self.prompt(update=update, context=context)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Resets the conversation.
        """
        if not await is_allowed(self.config, update, context):
            logging.warning(
                f"User {update.message.from_user.name} (id: {update.message.from_user.id}) "
                f"is not allowed to reset the conversation"
            )
            await self.send_disallowed_message(update, context)
            return

        logging.info(
            f"Resetting the conversation for user {update.message.from_user.name} "
            f"(id: {update.message.from_user.id})..."
        )

        chat_id = update.effective_chat.id
        user_id = update.message.from_user.id
        user_settings = self.usage[user_id].get_user_setting()
        user_brain = user_settings["brain"]
        brain_prompt = chat_modes[user_brain]["prompt_start"]
        reset_content = brain_prompt

        self.openai.reset_chat_history(chat_id=chat_id, content=reset_content)
        await update.effective_message.reply_text(
            message_thread_id=get_thread_id(update),
            text=localized_text("reset_done", self.config.bot_language),
        )

    async def image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Generates an image for the given prompt using DALL·E APIs
        """
        if (
                not self.config.enable_image_generation
                or not await self.check_allowed_and_within_budget(update, context)
        ):
            return

        image_query = message_text(update.message)
        if image_query == "":
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=localized_text("image_no_prompt", self.config.bot_language),
            )
            return

        logging.info(
            f"New image generation request received from user {update.message.from_user.name} "
            f"(id: {update.message.from_user.id})"
        )

        async def _generate():
            try:
                image_url, image_size = await self.openai.generate_image(
                    prompt=image_query
                )
                if self.config.image_receive_mode == "photo":
                    await update.effective_message.reply_photo(
                        reply_to_message_id=get_reply_to_message_id(
                            self.config, update
                        ),
                        photo=image_url,
                    )
                elif self.config.image_receive_mode == "document":
                    await update.effective_message.reply_document(
                        reply_to_message_id=get_reply_to_message_id(
                            self.config, update
                        ),
                        document=image_url,
                    )
                else:
                    raise Exception(
                        f"env variable IMAGE_RECEIVE_MODE has invalid value {self.config.image_receive_mode}"
                    )
                # add image request to users usage tracker
                user_id = update.message.from_user.id
                self.usage[user_id].add_image_request(
                    image_size, self.config.image_prices
                )
                # add guest chat request to guest usage tracker
                if (
                        str(user_id) not in self.config.allowed_user_ids.split(",")
                        and "guests" in self.usage
                ):
                    self.usage["guests"].add_image_request(
                        image_size, self.config.image_prices
                    )

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=f"{localized_text('image_fail', self.config.bot_language)}: {str(e)}",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )

        await wrap_with_indicator(
            update, context, _generate, constants.ChatAction.UPLOAD_PHOTO
        )

    async def tts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Generates a speech for the given input using TTS APIs
        """
        if (
                not self.config.enable_tts_generation
                or not await self.check_allowed_and_within_budget(update, context)
        ):
            return

        tts_query = message_text(update.message)
        if tts_query == "":
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=localized_text("tts_no_prompt", self.config.bot_language),
            )
            return

        logging.info(
            f"New speech generation request received from user {update.message.from_user.name} "
            f"(id: {update.message.from_user.id})"
        )

        async def _generate():
            try:
                speech_file, text_length = await self.openai.generate_speech(
                    prompt=tts_query
                )

                await update.effective_message.reply_voice(
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    voice=speech_file,
                )
                speech_file.close()
                # add image request to users usage tracker
                user_id = update.message.from_user.id
                self.usage[user_id].add_tts_request(
                    text_length, self.config.tts_model, self.config.tts_prices
                )
                # add guest chat request to guest usage tracker
                if (
                        str(user_id) not in self.config.allowed_user_ids.split(",")
                        and "guests" in self.usage
                ):
                    self.usage["guests"].add_tts_request(
                        text_length, self.config.tts_model, self.config.tts_prices
                    )

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=f"{localized_text('tts_fail', self.config.bot_language)}: {str(e)}",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )

        await wrap_with_indicator(
            update, context, _generate, constants.ChatAction.UPLOAD_VOICE
        )

    async def transcribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Transcribe audio messages.
        """
        if (
                not self.config.enable_transcription
                or not await self.check_allowed_and_within_budget(update, context)
        ):
            return

        if is_group_chat(update) and self.config.ignore_group_transcriptions:
            logging.info(f"Transcription coming from group chat, ignoring...")
            return

        chat_id = update.effective_chat.id
        filename = update.message.effective_attachment.file_unique_id

        async def _execute():
            filename_mp3 = f"{filename}.mp3"
            bot_language = self.config.bot_language
            try:
                media_file = await context.bot.get_file(
                    update.message.effective_attachment.file_id
                )
                await media_file.download_to_drive(filename)
            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=(
                        f"{localized_text('media_download_fail', bot_language)[0]}: "
                        f"{str(e)}. {localized_text('media_download_fail', bot_language)[1]}"
                    ),
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
                return

            try:
                audio_track = AudioSegment.from_file(filename)
                audio_track.export(filename_mp3, format="mp3")
                logging.info(
                    f"New transcribe request received from user {update.message.from_user.name} "
                    f"(id: {update.message.from_user.id})"
                )

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=localized_text("media_type_fail", bot_language),
                )
                if os.path.exists(filename):
                    os.remove(filename)
                return

            user_id = update.message.from_user.id
            if user_id not in self.usage:
                self.usage[user_id] = UsageTracker.create(
                    user_id, update.message.from_user.name
                )

            try:
                transcript = await self.openai.transcribe(filename_mp3)

                transcription_price = self.config.transcription_price
                self.usage[user_id].add_transcription_seconds(
                    audio_track.duration_seconds, transcription_price
                )

                allowed_user_ids = self.config.allowed_user_ids.split(",")
                if str(user_id) not in allowed_user_ids and "guests" in self.usage:
                    self.usage["guests"].add_transcription_seconds(
                        audio_track.duration_seconds, transcription_price
                    )

                # check if transcript starts with any of the prefixes
                response_to_transcription = any(
                    transcript.lower().startswith(prefix.lower()) if prefix else False
                    for prefix in self.config.voice_reply_prompts
                )

                if self.config.voice_reply_transcript and not response_to_transcription:
                    # Split into chunks of 4096 characters (Telegram's message limit)
                    transcript_output = f"_{localized_text('transcript', bot_language)}:_\n\"{transcript}\""
                    chunks = split_into_chunks(transcript_output)

                    for index, transcript_chunk in enumerate(chunks):
                        await update.effective_message.reply_text(
                            message_thread_id=get_thread_id(update),
                            reply_to_message_id=(
                                get_reply_to_message_id(self.config, update)
                                if index == 0
                                else None
                            ),
                            text=transcript_chunk,
                            parse_mode=constants.ParseMode.MARKDOWN,
                        )
                else:
                    # Get the response of the transcript
                    response, total_tokens = await self.openai.get_chat_response(
                        chat_id=chat_id, query=transcript
                    )

                    self.usage[user_id].add_chat_tokens(
                        total_tokens, self.config.token_price
                    )
                    if str(user_id) not in allowed_user_ids and "guests" in self.usage:
                        self.usage["guests"].add_chat_tokens(
                            total_tokens, self.config.token_price
                        )

                    # Split into chunks of 4096 characters (Telegram's message limit)
                    transcript_output = (
                        f"_{localized_text('transcript', bot_language)}:_\n\"{transcript}\"\n\n"
                        f"_{localized_text('answer', bot_language)}:_\n{response}"
                    )
                    chunks = split_into_chunks(transcript_output)

                    for index, transcript_chunk in enumerate(chunks):
                        await update.effective_message.reply_text(
                            message_thread_id=get_thread_id(update),
                            reply_to_message_id=(
                                get_reply_to_message_id(self.config, update)
                                if index == 0
                                else None
                            ),
                            text=transcript_chunk,
                            parse_mode=constants.ParseMode.MARKDOWN,
                        )

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=f"{localized_text('transcribe_fail', bot_language)}: {str(e)}",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            finally:
                if os.path.exists(filename_mp3):
                    os.remove(filename_mp3)
                if os.path.exists(filename):
                    os.remove(filename)

        await wrap_with_indicator(
            update, context, _execute, constants.ChatAction.TYPING
        )

    async def vision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Interpret image using vision model.
        """
        if (
                not self.config.enable_vision
                or not await self.check_allowed_and_within_budget(update, context)
        ):
            return

        chat_id = update.effective_chat.id
        prompt = update.message.caption

        if is_group_chat(update):
            if self.config.ignore_group_vision:
                logging.info(f"Vision coming from group chat, ignoring...")
                return
            else:
                trigger_keyword = self.config.group_trigger_keyword
                if (prompt is None and trigger_keyword != "") or (
                        prompt is not None
                        and not prompt.lower().startswith(trigger_keyword.lower())
                ):
                    logging.info(
                        f"Vision coming from group chat with wrong keyword, ignoring..."
                    )
                    return

        image = update.message.effective_attachment[-1]

        async def _execute():
            bot_language = self.config.bot_language
            try:
                media_file = await context.bot.get_file(image.file_id)
                temp_file = io.BytesIO(await media_file.download_as_bytearray())
            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=(
                        f"{localized_text('media_download_fail', bot_language)[0]}: "
                        f"{str(e)}. {localized_text('media_download_fail', bot_language)[1]}"
                    ),
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
                return

            # convert jpg from telegram to png as understood by openai

            temp_file_png = io.BytesIO()

            try:
                original_image = Image.open(temp_file)

                original_image.save(temp_file_png, format="PNG")
                logging.info(
                    f"New vision request received from user {update.message.from_user.name} "
                    f"(id: {update.message.from_user.id})"
                )

            except Exception as e:
                logging.exception(e)
                await update.effective_message.reply_text(
                    message_thread_id=get_thread_id(update),
                    reply_to_message_id=get_reply_to_message_id(self.config, update),
                    text=localized_text("media_type_fail", bot_language),
                )

            user_id = update.message.from_user.id
            if user_id not in self.usage:
                self.usage[user_id] = UsageTracker.create(
                    user_id, update.message.from_user.name
                )

            if self.config.stream:
                stream_response = self.openai.interpret_image_stream(
                    chat_id=chat_id, file_obj=temp_file_png, prompt=prompt
                )
                i = 0
                prev = ""
                sent_message = None
                backoff = 0
                stream_chunk = 0

                async for content, tokens in stream_response:
                    if is_direct_result(content):
                        return await handle_direct_result(self.config, update, content)

                    if len(content.strip()) == 0:
                        continue

                    stream_chunks = split_into_chunks(content)
                    if len(stream_chunks) > 1:
                        content = stream_chunks[-1]
                        if stream_chunk != len(stream_chunks) - 1:
                            stream_chunk += 1
                            try:
                                await edit_message_with_retry(
                                    context,
                                    chat_id,
                                    str(sent_message.message_id),
                                    stream_chunks[-2],
                                )
                            except:
                                pass
                            try:
                                sent_message = (
                                    await update.effective_message.reply_text(
                                        message_thread_id=get_thread_id(update),
                                        text=content if len(content) > 0 else "...",
                                    )
                                )
                            except:
                                pass
                            continue

                    cutoff = get_stream_cutoff_values(update, content)
                    cutoff += backoff

                    if i == 0:
                        try:
                            if sent_message is not None:
                                await context.bot.delete_message(
                                    chat_id=sent_message.chat_id,
                                    message_id=sent_message.message_id,
                                )
                            sent_message = await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(
                                    self.config, update
                                ),
                                text=content,
                            )
                        except:
                            continue

                    elif (
                            abs(len(content) - len(prev)) > cutoff
                            or tokens != "not_finished"
                    ):
                        prev = content

                        try:
                            use_markdown = tokens != "not_finished"
                            await edit_message_with_retry(
                                context,
                                chat_id,
                                str(sent_message.message_id),
                                text=content,
                                markdown=use_markdown,
                            )

                        except RetryAfter as e:
                            backoff += 5
                            await asyncio.sleep(e.retry_after)
                            continue

                        except TimedOut:
                            backoff += 5
                            await asyncio.sleep(0.5)
                            continue

                        except Exception:
                            backoff += 5
                            continue

                        await asyncio.sleep(0.01)

                    i += 1
                    if tokens != "not_finished":
                        total_tokens = int(tokens)

            else:
                try:
                    interpretation, total_tokens = await self.openai.interpret_image(
                        chat_id, temp_file_png, prompt=prompt
                    )

                    try:
                        await update.effective_message.reply_text(
                            message_thread_id=get_thread_id(update),
                            reply_to_message_id=get_reply_to_message_id(
                                self.config, update
                            ),
                            text=interpretation,
                            parse_mode=constants.ParseMode.MARKDOWN,
                        )
                    except BadRequest:
                        try:
                            await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(
                                    self.config, update
                                ),
                                text=interpretation,
                            )
                        except Exception as e:
                            logging.exception(e)
                            await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(
                                    self.config, update
                                ),
                                text=f"{localized_text('vision_fail', bot_language)}: {str(e)}",
                                parse_mode=constants.ParseMode.MARKDOWN,
                            )
                except Exception as e:
                    logging.exception(e)
                    await update.effective_message.reply_text(
                        message_thread_id=get_thread_id(update),
                        reply_to_message_id=get_reply_to_message_id(
                            self.config, update
                        ),
                        text=f"{localized_text('vision_fail', bot_language)}: {str(e)}",
                        parse_mode=constants.ParseMode.MARKDOWN,
                    )
            vision_token_price = self.config.vision_token_price
            logging.info(
                f"the vision token price {vision_token_price}, and the total tokens are: {total_tokens}"
            )
            self.usage[user_id].add_vision_tokens(total_tokens, vision_token_price)

            allowed_user_ids = self.config.allowed_user_ids.split(",")
            if str(user_id) not in allowed_user_ids and "guests" in self.usage:
                self.usage["guests"].add_vision_tokens(total_tokens, vision_token_price)

        await wrap_with_indicator(
            update, context, _execute, constants.ChatAction.TYPING
        )

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # TODO here add the modes
        """
        React to incoming messages and respond accordingly.
        """
        is_image: bool = False
        if update.edited_message or not update.message or update.message.via_bot:
            return

        if not await self.check_allowed_and_within_budget(update, context):
            return

        logging.info(
            f"New message received from user {update.message.from_user.name} (id: {update.message.from_user.id})"
        )
        chat_id = update.effective_chat.id
        user_id = update.message.from_user.id
        prompt = message_text(update.message)
        self.last_message[chat_id] = prompt

        if is_group_chat(update):
            trigger_keyword = self.config.group_trigger_keyword

            if prompt.lower().startswith(
                    trigger_keyword.lower()
            ) or update.message.text.lower().startswith("/chat"):
                if prompt.lower().startswith(trigger_keyword.lower()):
                    prompt = prompt[len(trigger_keyword):].strip()

                if (
                        update.message.reply_to_message
                        and update.message.reply_to_message.text
                        and update.message.reply_to_message.from_user.id != context.bot.id
                ):
                    prompt = f'"{update.message.reply_to_message.text}" {prompt}'
            else:
                if (
                        update.message.reply_to_message
                        and update.message.reply_to_message.from_user.id == context.bot.id
                ):
                    logging.info("Message is a reply to the bot, allowing...")
                else:
                    logging.warning(
                        "Message does not start with trigger keyword, ignoring..."
                    )
                    return

        try:
            total_tokens: float = 0
            if self.config.stream:
                await update.effective_message.reply_chat_action(
                    action=constants.ChatAction.TYPING,
                    message_thread_id=get_thread_id(update),
                )
                stream_response = self.openai.get_chat_response_stream(
                    chat_id=chat_id, query=prompt
                )
                i = 0
                prev = ""
                sent_message = None
                backoff = 0
                stream_chunk = 0

                async for content, tokens, image_used in stream_response:
                    if image_used:
                        is_image: bool = True
                    if is_direct_result(content):
                        return await handle_direct_result(self.config, update, content)
                    if len(content.strip()) == 0:
                        continue

                    stream_chunks = split_into_chunks(content)
                    if len(stream_chunks) > 1:
                        content = stream_chunks[-1]
                        if stream_chunk != len(stream_chunks) - 1:
                            stream_chunk += 1
                            try:
                                await edit_message_with_retry(
                                    context,
                                    chat_id,
                                    str(sent_message.message_id),
                                    stream_chunks[-2],
                                )
                            except:
                                pass
                            try:
                                sent_message = (
                                    await update.effective_message.reply_text(
                                        message_thread_id=get_thread_id(update),
                                        text=content if len(content) > 0 else "...",
                                    )
                                )
                            except:
                                pass
                            continue

                    cutoff = get_stream_cutoff_values(update, content)
                    cutoff += backoff

                    if i == 0:
                        try:
                            if sent_message is not None:
                                await context.bot.delete_message(
                                    chat_id=sent_message.chat_id,
                                    message_id=sent_message.message_id,
                                )
                            sent_message = await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=get_reply_to_message_id(
                                    self.config, update
                                ),
                                text=content,
                            )
                        except:
                            continue

                    elif (
                            abs(len(content) - len(prev)) > cutoff
                            or tokens != "not_finished"
                    ):
                        prev = content

                        try:
                            use_markdown = tokens != "not_finished"
                            await edit_message_with_retry(
                                context,
                                chat_id,
                                str(sent_message.message_id),
                                text=content,
                                markdown=use_markdown,
                            )

                        except RetryAfter as e:
                            backoff += 5
                            await asyncio.sleep(e.retry_after)
                            continue

                        except TimedOut:
                            backoff += 5
                            await asyncio.sleep(0.5)
                            continue

                        except Exception:
                            backoff += 5
                            continue

                        await asyncio.sleep(0.01)

                    i += 1
                    if tokens != "not_finished":
                        total_tokens = float(tokens)

            else:

                async def _reply():
                    nonlocal total_tokens
                    response, total_tokens = await self.openai.get_chat_response(
                        chat_id=chat_id, query=prompt
                    )

                    if is_direct_result(response):
                        return await handle_direct_result(self.config, update, response)

                    # Split into chunks of 4096 characters (Telegram's message limit)
                    chunks = split_into_chunks(response)

                    for index, chunk in enumerate(chunks):
                        try:
                            await update.effective_message.reply_text(
                                message_thread_id=get_thread_id(update),
                                reply_to_message_id=(
                                    get_reply_to_message_id(self.config, update)
                                    if index == 0
                                    else None
                                ),
                                text=chunk,
                                parse_mode=constants.ParseMode.MARKDOWN,
                            )
                        except Exception:
                            try:
                                await update.effective_message.reply_text(
                                    message_thread_id=get_thread_id(update),
                                    reply_to_message_id=(
                                        get_reply_to_message_id(self.config, update)
                                        if index == 0
                                        else None
                                    ),
                                    text=chunk,
                                )
                            except Exception as exception:
                                raise exception

                await wrap_with_indicator(
                    update, context, _reply, constants.ChatAction.TYPING
                )
            if is_image:
                # add image request to users usage tracker
                self.usage[user_id].add_image_request(
                    self.config.image_size, self.config.image_prices
                )
                # add guest chat request to guest usage tracker
                if (
                        str(user_id) not in self.config.allowed_user_ids.split(",")
                        and "guests" in self.usage
                ):
                    self.usage["guests"].add_image_request(
                        self.config.image_size, self.config.image_prices
                    )

            await add_chat_request_to_usage_tracker(
                self.usage, self.config, user_id, total_tokens
            )

        except Exception as e:
            logging.exception(e)
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                reply_to_message_id=get_reply_to_message_id(self.config, update),
                text=f"{localized_text('chat_fail', self.config.bot_language)} {str(e)}",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

    async def redeem(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Prompt user for the redeem code."""
        await update.message.reply_text(localized_text("redeem_me", self.config.bot_language))
        return self.REDEEM_CODE

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the conversation."""
        await update.message.reply_text(localized_text("redeem_cancel", self.config.bot_language))
        return ConversationHandler.END

    async def redeem_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        redeem_query = message_text(update.message)
        await update.message.reply_text(localized_text("redeem_working_on_it", self.config.bot_language))
        if redeem_query == "":
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=localized_text("redeem_no_prompt", self.config.bot_language),
            )
            return

        user = update.message.from_user
        user_id: int = user.id
        ex_user_id: str = ""
        if len(redeem_query) < 16:
            await update.message.reply_text(
                localized_text("short_redeem_code", self.config.bot_language)
            )
            return
        elif len(redeem_query) > 16:
            await update.message.reply_text(
                localized_text("long_redeem_code", self.config.bot_language)
            )
            return

        _, resp = await payment_switcher(
            user_id=user_id, redeem_card=redeem_query, user_payment_choice="anis-usdt"
        )
        # TODO test this really important
        if resp["success"]:
            place_holder = {'redeem_query': redeem_query, 'username': user.username}
            await update.message.reply_text(
                localized_text("prcessing_redeem", self.config.bot_language, **place_holder)
            )
            amount = resp["amount"]
            identity_no = resp["identityNo"]
            match = re.match(r"(\d+)", identity_no.split("-")[0])
            if match:
                if match.group(0) != "redeem":
                    raise ValueError(f"Invalid identity number: {identity_no}")
                ex_user_id = match.group(1)
            logging.info(f"User ID: {ex_user_id}")
            if ex_user_id == user_id:
                resp = self.usage[user_id].add_balance(amount=amount, payment_method="anis-usdt")
                if resp:
                    await update.message.reply_text(
                        localized_text("success_redeem", bot_language=self.config.bot_language)
                    )
            else:
                raise ValueError("Invalid user")
        else:
            await update.message.reply_text(
                localized_text("not_success_redeem", bot_language=self.config.bot_language)
            )
        return ConversationHandler.END

    async def handle_payments_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_username = update.callback_query.from_user.username
        query = update.callback_query
        # Extract plan type from callback data
        query_data = query.data
        logging.info(f"this is the call back from the {query_data}")
        _, payment_selected = query_data.split("|")
        logging.info(f"the payments {payment_selected}")
        # clean the name of the payments
        clean_payment_selected = clean_string(payment_selected)
        # Fetch plan details from your database or config
        logging.info(f"the clean payments {clean_payment_selected}")
        get_image = get_plan_image(clean_payment_selected, config=self.config)
        logging.info(clean_payment_selected)
        bot_language = self.config.bot_language

        payment_info = localized_text(f"payment_{clean_payment_selected}", bot_language)
        logging.info(f"the payments info {payment_info}")
        if clean_payment_selected == "libyan-payments" and plans[clean_payment_selected]["price"] is not None:
            buttons = []
            for price in plans[clean_payment_selected]["price"]:
                button_text = (
                    f"{price} {plans[clean_payment_selected]['currency'][0]}"
                )
                buttons.append(
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"prices|{price}|{clean_payment_selected}",
                    )
                )
            button_rows = [buttons[i: i + 3] for i in range(0, len(buttons), 3)]
            new_reply_markup = InlineKeyboardMarkup(button_rows)
            # temporary_info = "Hit the the link to start paying in Libyan currency through various methods (bank card - Pay for me - Mobi Cash - Sadad - Tadawul)"
            # temporary_info_ar = "🔗 اضغط على الرابط لبدء الدفع بالدينار الليبي من خلال الطرق المتعددة (بطاقة البنك - ادفع عني - موبي كاش - سداد - تداول)"
            # user_username_alert = f"Please write your username >> {user_username} << like in the following screenshot"
            user_username_alert_ar = f" يرجى كتابة اسم المستخدم الخاص بك {user_username} كما هو موضح في الصورة "

            # payment_link = "https://tlync.pay.net.ly/n2KQPY5bb4GezLDmMxrwRkvyBdJpqV9ABwZajoE2nO08l1gKAXP5Y7Q6NdGALaMR"
            alert = localized_text("libyan_payment_alert_link", bot_language)
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=get_image,
                caption=localized_text("payment_libyan-payments", self.config.bot_language),
                parse_mode="HTML",
                reply_markup=new_reply_markup
            )

        if clean_payment_selected == "crypto" and plans[clean_payment_selected]["price"] is not None:
            buttons = []
            for price in plans[clean_payment_selected]["price"]:
                button_text = (
                    f"{price} {plans[clean_payment_selected]['currency'][0]}"
                )
                buttons.append(
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"prices|{price}|{clean_payment_selected}",
                    )
                )

            # Divide buttons into rows of 3 buttons each
            button_rows = [buttons[i: i + 3] for i in range(0, len(buttons), 3)]
            new_reply_markup = InlineKeyboardMarkup(button_rows)

            # Send the image with the caption
            reply_markup_to_use = (
                new_reply_markup
                if isinstance(new_reply_markup, InlineKeyboardMarkup)
                else None
            )
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=get_image,
                caption=payment_info,
                parse_mode="HTML",
                reply_markup=reply_markup_to_use,
            )

        if clean_payment_selected == "anis-usdt" and plans[clean_payment_selected]["price"] is None:
            await context.bot.send_photo(
                chat_id=query.message.chat.id,
                photo=get_image,
                # caption=payment_info[0],
                caption=localized_text("coming_soon", self.config.bot_language),
                parse_mode="HTML",
            )
            # time.sleep(0.2)
            # await context.bot.send_message(
            #     text=f"{payment_info[1]}",
            #     chat_id=query.message.chat.id,
            # )

    async def pay_the_plane_handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.callback_query.from_user.id
        user_name = update.callback_query.from_user.name
        query = update.callback_query
        # Extract plan type from callback data
        query_data = query.data
        logging.info(f"this is the all price and plan {query_data}")
        bot_language = self.config.bot_language
        payment_link = localized_text("payment_link", bot_language)
        logging.info(f"the payment link is {payment_link}")
        _, amount_to_pay, payment_plan = query_data.split("|")
        if payment_plan == "crypto":
            url, order_id = payment_switcher(
                user_id=user_id, payment_plan=amount_to_pay, user_payment_choice=payment_plan
            )
            if url:
                caption = f"{payment_link} {amount_to_pay} {plans[payment_plan]['currency'][0]}\n<a href='{url}'>Pay Now</a>"

                text = localized_text("payment_crypto", bot_language)
                caption += text

                # Send the image with the caption
                await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text=caption,
                    parse_mode="HTML",
                )
        if payment_plan == "libyan-payments":
            custom_ref = f"{user_id}-{uuid4()}"
            data = {
                "id": self.config.tlync_storid,
                "amount": amount_to_pay,
                "phone": "0910000000",
                "email": "text@email.com",
                "backend_url": self.config.supabase_tlync_webhook,
                "frontend_url": "http://frontend.url",
                "custom_ref": custom_ref
            }
            logging.info(f"this is the request body {data}")
            logging.info(f"the payment plan is {payment_plan}")
            res = payment_switcher(user_payment_choice=payment_plan, data=DataBody(**data))
            logging.info(f"the response of the libyan payments is {res.json()}")
            res_body = res.json()
            if res_body:
                if "result" in res_body:
                    if res_body["result"] == "success" and res_body["custom_ref"] == custom_ref:
                        url = res_body["url"]
                        caption = f"{payment_link} {amount_to_pay} {plans[payment_plan]['currency'][0]}\n<a href='{url}'>Pay Now</a>"

                        text = localized_text("payment_libyan-payments", bot_language)
                        caption += text

                        # Send the image with the caption
                        await context.bot.send_message(
                            chat_id=query.message.chat.id,
                            text=caption,
                            parse_mode="HTML",
                        )

    async def payment_handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        bot_language = self.config.bot_language
        # Since we're not handling the callback queries anymore,
        # we only proceed if it's not a callback query
        if not update.callback_query:
            text = f"{localized_text('payments', bot_language=bot_language)}"

            # Create subscription buttons
            button_text, reply_markup = await get_payments_buttons()

            # Send the message with buttons
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,  # Include the reply_markup with buttons
            )

    async def inline_query(
            self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle the inline query. This is run when you type: @botusername <query>
        """
        query = update.inline_query.query
        if len(query) < 3:
            return
        if not await self.check_allowed_and_within_budget(
                update, context, is_inline=True
        ):
            return

        callback_data_suffix = "gpt:"
        result_id = str(uuid4())
        self.inline_queries_cache[result_id] = query
        callback_data = f"{callback_data_suffix}{result_id}"

        await self.send_inline_query_result(
            update, result_id, message_content=query, callback_data=callback_data
        )

    async def send_inline_query_result(
            self, update: Update, result_id, message_content, callback_data=""
    ):
        """
        Send inline query result
        """
        try:
            reply_markup = None
            bot_language = self.config.bot_language
            if callback_data:
                reply_markup = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=f'🤖 {localized_text("answer_with_chatgpt", bot_language)}',
                                callback_data=callback_data,
                            )
                        ]
                    ]
                )

            inline_query_result = InlineQueryResultArticle(
                id=result_id,
                title=localized_text("ask_chatgpt", bot_language),
                input_message_content=InputTextMessageContent(message_content),
                description=message_content,
                thumb_url="https://user-images.githubusercontent.com/11541888/223106202-7576ff11-2c8e-408d-94ea"
                          "-b02a7a32149a.png",
                reply_markup=reply_markup,
            )

            await update.inline_query.answer([inline_query_result], cache_time=0)
        except Exception as e:
            logging.error(
                f"An error occurred while generating the result card for inline query {e}"
            )

    async def handle_callback_inline_query(
            self, update: Update, context: CallbackContext
    ):
        """
        Handle the callback query from the inline query result
        """
        callback_data = update.callback_query.data
        user_id = update.callback_query.from_user.id
        inline_message_id = update.callback_query.inline_message_id
        name = update.callback_query.from_user.name
        callback_data_suffix = "gpt:"
        query = ""
        bot_language = self.config.bot_language
        answer_tr = localized_text("answer", bot_language)
        loading_tr = localized_text("loading", bot_language)

        try:
            if callback_data.startswith(callback_data_suffix):
                unique_id = callback_data.split(":")[1]
                total_tokens = 0

                # Retrieve the prompt from the cache
                query = self.inline_queries_cache.get(unique_id)
                if query:
                    self.inline_queries_cache.pop(unique_id)
                else:
                    error_message = (
                        f'{localized_text("error", bot_language)}. '
                        f'{localized_text("try_again", bot_language)}'
                    )
                    await edit_message_with_retry(
                        context,
                        chat_id=None,
                        message_id=inline_message_id,
                        text=f"{query}\n\n_{answer_tr}:_\n{error_message}",
                        is_inline=True,
                    )
                    return

                unavailable_message = localized_text(
                    "function_unavailable_in_inline_mode", bot_language
                )
                if self.config.stream:
                    stream_response = self.openai.get_chat_response_stream(
                        chat_id=user_id, query=query
                    )
                    i = 0
                    prev = ""
                    backoff = 0
                    async for content, tokens in stream_response:
                        if is_direct_result(content):
                            cleanup_intermediate_files(content)
                            await edit_message_with_retry(
                                context,
                                chat_id=None,
                                message_id=inline_message_id,
                                text=f"{query}\n\n_{answer_tr}:_\n{unavailable_message}",
                                is_inline=True,
                            )
                            return

                        if len(content.strip()) == 0:
                            continue

                        cutoff = get_stream_cutoff_values(update, content)
                        cutoff += backoff

                        if i == 0:
                            try:
                                await edit_message_with_retry(
                                    context,
                                    chat_id=None,
                                    message_id=inline_message_id,
                                    text=f"{query}\n\n{answer_tr}:\n{content}",
                                    is_inline=True,
                                )
                            except:
                                continue

                        elif (
                                abs(len(content) - len(prev)) > cutoff
                                or tokens != "not_finished"
                        ):
                            prev = content
                            try:
                                use_markdown = tokens != "not_finished"
                                divider = "_" if use_markdown else ""
                                text = f"{query}\n\n{divider}{answer_tr}:{divider}\n{content}"

                                # We only want to send the first 4096 characters. No chunking allowed in inline mode.
                                text = text[:4096]

                                await edit_message_with_retry(
                                    context,
                                    chat_id=None,
                                    message_id=inline_message_id,
                                    text=text,
                                    markdown=use_markdown,
                                    is_inline=True,
                                )

                            except RetryAfter as e:
                                backoff += 5
                                await asyncio.sleep(e.retry_after)
                                continue
                            except TimedOut:
                                backoff += 5
                                await asyncio.sleep(0.5)
                                continue
                            except Exception:
                                backoff += 5
                                continue

                            await asyncio.sleep(0.01)

                        i += 1
                        if tokens != "not_finished":
                            total_tokens = int(tokens)

                else:

                    async def _send_inline_query_response():
                        nonlocal total_tokens
                        # Edit the current message to indicate that the answer is being processed
                        await context.bot.edit_message_text(
                            inline_message_id=inline_message_id,
                            text=f"{query}\n\n_{answer_tr}:_\n{loading_tr}",
                            parse_mode=constants.ParseMode.MARKDOWN,
                        )

                        logging.info(f"Generating response for inline query by {name}")
                        response, total_tokens = await self.openai.get_chat_response(
                            chat_id=user_id, query=query
                        )

                        if is_direct_result(response):
                            cleanup_intermediate_files(response)
                            await edit_message_with_retry(
                                context,
                                chat_id=None,
                                message_id=inline_message_id,
                                text=f"{query}\n\n_{answer_tr}:_\n{unavailable_message}",
                                is_inline=True,
                            )
                            return

                        text_content = f"{query}\n\n_{answer_tr}:_\n{response}"

                        # We only want to send the first 4096 characters. No chunking allowed in inline mode.
                        text_content = text_content[:4096]

                        # Edit the original message with the generated content
                        await edit_message_with_retry(
                            context,
                            chat_id=None,
                            message_id=inline_message_id,
                            text=text_content,
                            is_inline=True,
                        )

                    await wrap_with_indicator(
                        update,
                        context,
                        _send_inline_query_response,
                        constants.ChatAction.TYPING,
                        is_inline=True,
                    )

                await add_chat_request_to_usage_tracker(
                    self.usage, self.config, user_id, total_tokens
                )

        except Exception as e:
            logging.error(
                f"Failed to respond to an inline query via button callback: {e}"
            )
            logging.exception(e)
            localized_answer = localized_text("chat_fail", self.config.bot_language)
            await edit_message_with_retry(
                context,
                chat_id=None,
                message_id=inline_message_id,
                text=f"{query}\n\n_{answer_tr}:_\n{localized_answer} {str(e)}",
                is_inline=True,
            )

    # TODO check this function
    async def check_allowed_and_within_budget(
            self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_inline=False
    ) -> bool:
        """
        Checks if the user is allowed to use the bot and if they are within their budget
        :param update: Telegram update object
        :param context: Telegram context object
        :param is_inline: Boolean flag for inline queries
        :return: Boolean indicating if the user is allowed to use the bot
        """
        name = (
            update.inline_query.from_user.name
            if is_inline
            else update.message.from_user.name
        )
        user_id = (
            update.inline_query.from_user.id
            if is_inline
            else update.message.from_user.id
        )

        if not await is_allowed(self.config, update, context, is_inline=is_inline):
            logging.warning(
                f"User {name} (id: {user_id}) is not allowed to use the bot"
            )
            await self.send_disallowed_message(update, context, is_inline)
            return False
        if not await is_within_budget(
                self.config, self.usage, update, is_inline=is_inline
        ):
            logging.warning(f"User {name} (id: {user_id}) reached their usage limit")
            await self.send_budget_reached_message(update, context, is_inline)
            return False

        return True

    async def send_disallowed_message(
            self, update: Update, _: ContextTypes.DEFAULT_TYPE, is_inline=False
    ):
        """
        Sends the disallowed message to the user.
        """
        if not is_inline:
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update),
                text=self.disallowed_message,
                disable_web_page_preview=True,
            )
        else:
            result_id = str(uuid4())
            await self.send_inline_query_result(
                update, result_id, message_content=self.disallowed_message
            )

    async def send_budget_reached_message(
            self, update: Update, _: ContextTypes.DEFAULT_TYPE, is_inline=False
    ):
        """
        Sends the budget reached message to the user.
        """
        if not is_inline:
            await update.effective_message.reply_text(
                message_thread_id=get_thread_id(update), text=self.budget_limit_message
            )
        else:
            result_id = str(uuid4())
            await self.send_inline_query_result(
                update, result_id, message_content=self.budget_limit_message
            )

    async def post_init(self, application: Application) -> None:
        """
        Post initialization hook for the bot.
        """
        try:
            await application.bot.set_my_commands(
                self.group_commands, scope=BotCommandScopeAllGroupChats()
            )
            logging.info("Group commands set successfully.")
        except Exception as e:
            logging.error(f"Failed to set group commands: {e}")

        try:
            await application.bot.set_my_commands(self.commands)
            logging.info("Commands set successfully.")
        except Exception as e:
            logging.error(f"Failed to set commands: {e}")
