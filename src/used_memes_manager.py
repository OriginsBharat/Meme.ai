import logging
import os

# The file where we will store the IDs of used memes.
USED_MEMES_LOG_FILE = "used_memes.log"

def get_used_meme_ids() -> set[str]:
    """
    Reads the log file and returns a set of all used meme IDs.

    Returns:
        set[str]: A set containing the IDs of all memes that have been used before.
                  Returns an empty set if the file doesn't exist or is empty.
    """
    if not os.path.exists(USED_MEMES_LOG_FILE):
        return set()

    try:
        with open(USED_MEMES_LOG_FILE, 'r') as f:
            # Read each line, strip whitespace, and filter out any empty lines.
            used_ids = {line.strip() for line in f if line.strip()}
        return used_ids
    except Exception as e:
        logging.error(f"Could not read used memes log file: {e}")
        return set()

def add_used_meme_ids(ids_to_add: list[str]):
    """
    Appends a list of new meme IDs to the log file.

    Args:
        ids_to_add (list[str]): A list of meme IDs to be added to the log.
    """
    if not ids_to_add:
        return

    try:
        with open(USED_MEMES_LOG_FILE, 'a') as f:
            for meme_id in ids_to_add:
                f.write(f"{meme_id}\n")
        logging.info(f"Successfully logged {len(ids_to_add)} used memes.")
    except Exception as e:
        logging.error(f"Could not write to used memes log file: {e}")