import logging
from elevenlabs import generate, save

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_tts_audio(api_key: str, text_to_speak: str, output_filepath: str, voice: str = "Laura", model: str = "eleven_multilingual_v2") -> str | None:
    """
    Generates TTS audio from the given text and saves it to a file.

    Args:
        api_key (str): The API key for the ElevenLabs service.
        text_to_speak (str): The text to be converted to speech.
        output_filepath (str): The path to save the generated MP3 file.
        voice (str): The name or ID of the voice to use. Defaults to "Laura".
        model (str): The model to use for generation.

    Returns:
        str | None: The path to the saved audio file on success, otherwise None.
    """
    if not text_to_speak:
        logging.warning("No text provided for TTS generation.")
        return None

    if not api_key:
        logging.error("ElevenLabs API key is missing.")
        return None

    logging.info(f"Generating TTS for text: \"{text_to_speak[:50]}...\" using voice '{voice}'.")
    try:
        # Generate the audio stream
        audio_stream = generate(
            api_key=api_key,
            text=text_to_speak,
            voice=voice,
            model=model
        )

        # Save the audio stream to the specified file
        save(audio_stream, output_filepath)

        logging.info(f"Successfully saved TTS audio to {output_filepath}")
        return output_filepath
    except Exception as e:
        logging.error(f"Failed to generate or save TTS audio: {e}", exc_info=True)
        return None
