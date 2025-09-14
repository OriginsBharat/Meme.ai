import logging
from elevenlabs import save
from elevenlabs.client import ElevenLabs

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TTSManager:
    """
    A manager class to handle interactions with the ElevenLabs API,
    using the officially documented methods.
    """
    def __init__(self, api_key: str):
        """
        Initializes the TTSManager with the user's ElevenLabs API key.

        Args:
            api_key (str): The API key for the ElevenLabs service.
        """
        if not api_key:
            raise ValueError("API key for ElevenLabs is required.")
        self.client = ElevenLabs(api_key=api_key)
        logging.info("ElevenLabs client initialized correctly.")

    def generate_tts_audio(self, text_to_speak: str, output_filepath: str, voice: str = "21m00Tcm4TlvDq8ikWAM", model: str = "eleven_multilingual_v2") -> str | None:
        """
        Generates TTS audio from the given text and saves it to a file.

        Args:
            text_to_speak (str): The text to be converted to speech.
            output_filepath (str): The path to save the generated MP3 file.
            voice (str): The name or ID of the voice to use. Defaults to "Rachel".
            model (str): The model to use for generation.

        Returns:
            str | None: The path to the saved audio file on success, otherwise None.
        """
        if not text_to_speak:
            logging.warning("No text provided for TTS generation.")
            return None

        logging.info(f"Generating TTS for text: \"{text_to_speak[:50]}...\" using voice '{voice}'.")
        try:
            # Generate the audio stream (which is a generator)
            audio_generator = self.client.text_to_speech.convert(
                text=text_to_speak,
                voice_id=voice, # The parameter is voice_id
                model_id=model,
            )

            # Use the library's save function to correctly handle the generator
            save(audio_generator, output_filepath)

            logging.info(f"Successfully saved TTS audio to {output_filepath}")
            return output_filepath
        except Exception as e:
            logging.error(f"Failed to generate or save TTS audio: {e}", exc_info=True)
            return None
