import logging
import os

from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    filters,
)
from telegram import constants
from plugin_manager import PluginManager
from openai_helper import OpenAIHelper
from telegram_bot import ChatGPTTelegramBot
from config import BotConfig
from utils import error_handler


load_dotenv()


def main():
    # Setup logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    bot_config = BotConfig()

    # Check if the required environment variables are set
    required_values = ["TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"]
    missing_values = [
        value for value in required_values if os.environ.get(value) is None
    ]
    if len(missing_values) > 0:
        logging.error(
            f'The following environment values are missing in your .env: {", ".join(missing_values)}'
        )
        exit(1)

    plugin_config = {"plugins": os.environ.get("PLUGINS", "").split(",")}

    # Setup and run ChatGPT and Telegram bot
    plugin_manager = PluginManager(config=plugin_config)
    openai_helper = OpenAIHelper(config=bot_config, plugin_manager=plugin_manager)
    telegram_bot = ChatGPTTelegramBot(config=bot_config, openai=openai_helper)

    # Instead of telegram_bot.run(), incorporate the run method here
    application = (
        ApplicationBuilder()
        .token(bot_config.telegram_token)
        .proxy(bot_config.proxy)  # Adjust these as per your actual config attributes
        .get_updates_proxy(bot_config.proxy)
        .post_init(telegram_bot.post_init)  # Adjust method references as needed
        .concurrent_updates(True)
        .build()
    )

    # Add all the handlers as in the run method
    application.add_handler(CommandHandler("reset", telegram_bot.reset))
    application.add_handler(CommandHandler("help", telegram_bot.help))
    application.add_handler(CommandHandler("image", telegram_bot.image))
    application.add_handler(CommandHandler("tts", telegram_bot.tts))
    application.add_handler(CommandHandler("start", telegram_bot.start))
    application.add_handler(CommandHandler("stats", telegram_bot.stats))
    application.add_handler(CommandHandler("resend", telegram_bot.resend))
    application.add_handler(CommandHandler("brains", telegram_bot.get_chat_modes))
    application.add_handler(CommandHandler("payments", telegram_bot.payment_handle))
    application.add_handler(
        CommandHandler(
            "chat",
            telegram_bot.prompt,
            filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP,
        )
    )
    application.add_handler(
        MessageHandler(filters.PHOTO | filters.Document.IMAGE, telegram_bot.vision)
    )
    application.add_handler(
        MessageHandler(
            filters.AUDIO
            | filters.VOICE
            | filters.Document.AUDIO
            | filters.VIDEO
            | filters.VIDEO_NOTE
            | filters.Document.VIDEO,
            telegram_bot.transcribe,
        )
    )
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), telegram_bot.prompt)
    )
    application.add_handler(
        InlineQueryHandler(
            telegram_bot.inline_query,
            chat_types=[
                constants.ChatType.GROUP,
                constants.ChatType.SUPERGROUP,
                constants.ChatType.PRIVATE,
            ],
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            telegram_bot.get_chat_modes_callback, pattern="^show_chat_modes"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            telegram_bot.set_chat_mode_handle, pattern="^set_chat_mode"
        )
    )
    application.add_handler(
        CallbackQueryHandler(telegram_bot.handle_callback_inline_query)
    )

    application.add_error_handler(error_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
