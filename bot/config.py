import yaml
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
import datetime

load_dotenv()

# Load chat modes
# Define the configuration directory
config_dir = Path(__file__).parent.parent.resolve() / "bot/resources"
with open(config_dir / "chat_modes.yml", "r") as f:
    chat_modes = yaml.safe_load(f)

config_dir = Path(__file__).parent.parent.resolve() / "bot/resources"
with open(config_dir / "plans.yml", "r") as f:
    plans = yaml.safe_load(f)

# Models can be found here: https://platform.openai.com/docs/models/overview
GPT_3_MODELS = ("gpt-3.5-turbo-0125",)
GPT_4_VISION_MODELS = ("gpt-4-vision-preview",)
GPT_4_128K_MODELS = ("gpt-4-0125-preview",)
GPT_ALL_MODELS = GPT_3_MODELS + GPT_4_VISION_MODELS + GPT_4_128K_MODELS


def default_max_tokens(model: str) -> int:
    """
    Gets the default number of max tokens for the given model.
    :param model: The model name
    :return: The default number of max tokens
    """
    base = 1200
    if model in GPT_3_MODELS:
        return base
    elif model in GPT_4_VISION_MODELS:
        return 4096
    elif model in GPT_4_128K_MODELS:
        return 4096


def are_functions_available(model: str) -> bool:
    """
    Whether the given model supports functions
    """
    # Deprecated models
    if model in ("gpt-3.5-turbo-0301", "gpt-4-0314", "gpt-4-32k-0314"):
        return False
    # Stable models will be updated to support functions on June 27, 2023
    if model in (
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-1106",
        "gpt-4",
        "gpt-4-32k",
        "gpt-4-1106-preview",
    ):
        return datetime.date.today() > datetime.date(2023, 6, 27)
    if model == "gpt-4-vision-preview":
        return False
    return True


# Setup configurations
model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
functions_available = are_functions_available(model=model)
max_tokens_default = default_max_tokens(model=model)


class BotConfig:
    def __init__(self):
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.show_usage = os.environ.get("SHOW_USAGE", "false").lower() == "true"
        self.stream = os.environ.get("STREAM", "true").lower() == "true"
        self.proxy = os.environ.get("PROXY", None) or os.environ.get(
            "OPENAI_PROXY", None
        )
        self.env = os.getenv("ENV", False)
        self.max_history_size = int(os.environ.get("MAX_HISTORY_SIZE", 15))
        self.max_conversation_age_minutes = int(
            os.environ.get("MAX_CONVERSATION_AGE_MINUTES", 180)
        )
        self.assistant_prompt = os.environ.get(
            "ASSISTANT_PROMPT", "You are a helpful assistant."
        )
        self.max_tokens = int(os.environ.get("MAX_TOKENS", max_tokens_default))
        self.n_choices = int(os.environ.get("N_CHOICES", 1))
        self.temperature = float(os.environ.get("TEMPERATURE", 1.0))
        self.image_model = os.environ.get("IMAGE_MODEL", "dall-e-2")
        self.image_quality = os.environ.get("IMAGE_QUALITY", "standard")
        self.image_style = os.environ.get("IMAGE_STYLE", "vivid")
        self.image_size = os.environ.get("IMAGE_SIZE", "512x512")
        self.enable_functions = (
            os.environ.get("ENABLE_FUNCTIONS", str(functions_available)).lower()
            == "true"
        )
        self.functions_max_consecutive_calls = int(
            os.environ.get("FUNCTIONS_MAX_CONSECUTIVE_CALLS", 10)
        )
        self.presence_penalty = float(os.environ.get("PRESENCE_PENALTY", 0.0))
        self.frequency_penalty = float(os.environ.get("FREQUENCY_PENALTY", 0.0))
        self.bot_language = os.environ.get("BOT_LANGUAGE", "en")
        self.show_plugins_used = (
            os.environ.get("SHOW_PLUGINS_USED", "false").lower() == "true"
        )
        self.whisper_prompt = os.environ.get("WHISPER_PROMPT", "")
        self.vision_model = os.environ.get("VISION_MODEL", "gpt-4-vision-preview")
        self.enable_vision_follow_up_questions = (
            os.environ.get("ENABLE_VISION_FOLLOW_UP_QUESTIONS", "true").lower()
            == "true"
        )
        self.vision_prompt = os.environ.get("VISION_PROMPT", "What is in this image")
        self.vision_detail = os.environ.get("VISION_DETAIL", "auto")
        self.vision_max_tokens = int(os.environ.get("VISION_MAX_TOKENS", "300"))
        self.tts_model = os.environ.get("TTS_MODEL", "tts-1")
        self.tts_voice = os.environ.get("TTS_VOICE", "alloy")
        self.admin_user_ids = os.environ.get("ADMIN_USER_IDS", "-")
        self.allowed_user_ids = os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "*")
        self.enable_quoting = os.environ.get("ENABLE_QUOTING", "true").lower() == "true"
        self.enable_image_generation = (
            os.environ.get("ENABLE_IMAGE_GENERATION", "true").lower() == "true"
        )
        self.enable_transcription = (
            os.environ.get("ENABLE_TRANSCRIPTION", "true").lower() == "true"
        )
        self.enable_vision = os.environ.get("ENABLE_VISION", "true").lower() == "true"
        self.enable_tts_generation = (
            os.environ.get("ENABLE_TTS_GENERATION", "true").lower() == "true"
        )
        self.budget_period = os.environ.get("BUDGET_PERIOD", "monthly").lower()
        self.user_budgets = os.environ.get(
            "USER_BUDGETS", os.environ.get("MONTHLY_USER_BUDGETS", "*")
        )
        self.guest_budget = float(
            os.environ.get(
                "GUEST_BUDGET", os.environ.get("MONTHLY_GUEST_BUDGET", "100.0")
            )
        )
        self.voice_reply_transcript = (
            os.environ.get("VOICE_REPLY_WITH_TRANSCRIPT_ONLY", "false").lower()
            == "true"
        )
        self.voice_reply_prompts = os.environ.get("VOICE_REPLY_PROMPTS", "").split(";")
        self.ignore_group_transcriptions = (
            os.environ.get("IGNORE_GROUP_TRANSCRIPTIONS", "true").lower() == "true"
        )
        self.ignore_group_vision = (
            os.environ.get("IGNORE_GROUP_VISION", "true").lower() == "true"
        )
        self.group_trigger_keyword = os.environ.get("GROUP_TRIGGER_KEYWORD", "")
        self.token_price = float(os.environ.get("TOKEN_PRICE", 0.002))
        self.image_prices = [
            float(i)
            for i in os.environ.get("IMAGE_PRICES", "0.016,0.018,0.02").split(",")
        ]
        self.vision_token_price = float(os.environ.get("VISION_TOKEN_PRICE", "0.01"))
        self.image_receive_mode = os.environ.get("IMAGE_FORMAT", "photo")
        self.tts_prices = [
            float(i) for i in os.environ.get("TTS_PRICES", "0.015,0.030").split(",")
        ]
        self.transcription_price = float(os.environ.get("TRANSCRIPTION_PRICE", 0.006))

        # Define model variable if it's not part of the environment variables
        self.model = model
        if self.enable_functions and not functions_available:
            logging.error(
                f"ENABLE_FUNCTIONS is set to true, but the model {model} does not support it. "
                f"Please set ENABLE_FUNCTIONS to false or use a model that supports it."
            )
            exit(1)
        # Initialize other configurations here

    def update_config(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
            # Optional: Add logic to persist changes
        else:
            raise AttributeError(f"No such configuration: {key}")

    def get_config(self, key):
        return getattr(self, key, None)
