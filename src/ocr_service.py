import pytesseract
import requests
import logging
from PIL import Image
import io
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def configure_tesseract(tesseract_cmd_path: str):
    """
    Configures the path to the Tesseract executable.
    This must be called once before using the OCR service.

    Args:
        tesseract_cmd_path (str): The full file path to the tesseract.exe.

    Returns:
        bool: True if the path was set, False otherwise.
    """
    if not tesseract_cmd_path:
        logging.error("Tesseract command path is not provided.")
        return False
    try:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd_path
        # Test if tesseract is working by getting its version
        version = pytesseract.get_tesseract_version()
        logging.info(f"Tesseract version {version} configured successfully.")
        return True
    except pytesseract.TesseractNotFoundError:
        logging.error(f"Tesseract not found at the specified path: {tesseract_cmd_path}. Please ensure Tesseract is installed and the path is correct.")
        return False
    except Exception as e:
        logging.error(f"An error occurred while configuring Tesseract: {e}")
        return False

def extract_text_from_image(image_source: str) -> str:
    """
    Extracts text from an image from either a local file path or a URL.

    Args:
        image_source (str): The local file path or URL of the image to process.

    Returns:
        str: The extracted text from the image. Returns an empty string if
             no text is found or if an error occurs.
    """
    logging.info(f"Attempting to extract text from image source: {image_source}")
    try:
        image = None
        # Check if the source is a URL or a local file
        if image_source.lower().startswith(('http://', 'https://')):
            # It's a URL, download it
            response = requests.get(image_source, stream=True, timeout=10)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
        else:
            # It's a local file path
            if not os.path.exists(image_source):
                logging.error(f"Image file not found at local path: {image_source}")
                return ""
            image = Image.open(image_source)

        # Use pytesseract to extract text
        extracted_text = pytesseract.image_to_string(image)

        logging.info(f"Successfully extracted text: \"{extracted_text.strip()}\"")
        return extracted_text.strip()

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download image from {image_source}: {e}")
        return ""
    except pytesseract.TesseractNotFoundError:
        logging.error("Tesseract is not installed or not in your PATH. Please configure it in Settings.")
        return ""
    except Exception as e:
        logging.error(f"An error occurred during OCR processing for {image_source}: {e}")
        return ""
