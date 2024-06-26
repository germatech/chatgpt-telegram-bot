import json
import logging
from typing import Any, Dict, List, Optional

from plugins.gtts_text_to_speech import GTTSTextToSpeech
from plugins.auto_tts import AutoTextToSpeech
from plugins.dice import DicePlugin
from plugins.youtube_audio_extractor import YouTubeAudioExtractorPlugin
from plugins.ddg_image_search import DDGImageSearchPlugin
from plugins.ddg_translate import DDGTranslatePlugin
from plugins.spotify import SpotifyPlugin
from plugins.crypto import CryptoPlugin
from plugins.weather import WeatherPlugin
from plugins.ddg_web_search import DDGWebSearchPlugin
from plugins.wolfram_alpha import WolframAlphaPlugin
from plugins.deepl import DeeplTranslatePlugin
from plugins.worldtimeapi import WorldTimeApiPlugin
from plugins.whois_ import WhoisPlugin
from plugins.webshot import WebshotPlugin
from plugins.dalle_3 import DallE3


class PluginManager:
    """
    A class to manage the plugins and call the correct functions,
    enhanced with error handling, logging, and type annotations.
    """

    def __init__(self, config: Dict[str, Any]):
        self.plugins = []
        self.initialize_plugins(config)

    def initialize_plugins(self, config: Dict[str, Any]):
        enabled_plugins = config.get("plugins", [])
        plugin_mapping = {
            "wolfram": WolframAlphaPlugin,
            "weather": WeatherPlugin,
            "crypto": CryptoPlugin,
            "ddg_web_search": DDGWebSearchPlugin,
            "ddg_translate": DDGTranslatePlugin,
            "ddg_image_search": DDGImageSearchPlugin,
            "spotify": SpotifyPlugin,
            "worldtimeapi": WorldTimeApiPlugin,
            "youtube_audio_extractor": YouTubeAudioExtractorPlugin,
            "dice": DicePlugin,
            "deepl_translate": DeeplTranslatePlugin,
            "gtts_text_to_speech": GTTSTextToSpeech,
            "auto_tts": AutoTextToSpeech,
            "whois": WhoisPlugin,
            "webshot": WebshotPlugin,
            "dalle": DallE3,
        }

        for plugin_key in enabled_plugins:
            plugin_cls = plugin_mapping.get(plugin_key)
            if plugin_cls:
                try:
                    # If plugin initialization becomes async, this part needs adjustment.
                    self.plugins.append(plugin_cls())
                except Exception as e:
                    logging.error(f"Error initializing plugin {plugin_key}: {e}")
            else:
                logging.warning(f"Plugin '{plugin_key}' not found in plugin_mapping.")

    def get_functions_specs(self) -> List[Dict[str, Any]]:
        """
        Return the list of function specs that can be called by the model.
        """
        return [spec for plugin in self.plugins for spec in plugin.get_spec()]

    async def call_function(self, function_name: str, helper: Any, **kwargs) -> str:
        """
        Call a function based on the name and parameters provided.
        """
        plugin = self.__get_plugin_by_function_name(function_name)
        if not plugin:
            error_message = {"error": f"Function {function_name} not found"}
            logging.error(error_message["error"])
            return json.dumps(error_message)

        try:
            result = await plugin.execute(function_name, helper, **kwargs)
            return json.dumps(result, default=str)
        except Exception as e:
            logging.error(f"Error executing function {function_name}: {e}")
            return json.dumps({"error": "An error occurred during plugin execution."})

    def get_plugin_source_name(self, function_name: str) -> str:
        """
        Return the source name of the plugin.
        """
        plugin = self.__get_plugin_by_function_name(function_name)
        if not plugin:
            logging.warning(f"Plugin for function '{function_name}' not found.")
            return ""
        return plugin.get_source_name()

    def __get_plugin_by_function_name(self, function_name: str) -> Optional[Any]:
        """
        Find the plugin that supports the given function name.
        """
        for plugin in self.plugins:
            if function_name in (spec.get("name") for spec in plugin.get_spec()):
                return plugin
        return None
