import logging
import asyncio
from twikit import Client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# A constant to store the cookie file path
COOKIE_FILE_PATH = 'x_cookies.json'

async def search_tweets_async(username, password, keyword, limit, after=None):
    """
    Asynchronous function to perform the tweet search, with pagination.
    """
    client = Client(language='en-US')

    try:
        logging.info("Attempting to log in to X/Twitter...")
        # Try to load cookies to avoid repeated logins
        try:
            await client.load_cookies(COOKIE_FILE_PATH)
            logging.info("X/Twitter session loaded from cookies.")
        except FileNotFoundError:
            logging.info("Cookie file not found, proceeding with login.")
            await client.login(
                auth_info_1=username,
                password=password
            )
            await client.save_cookies(COOKIE_FILE_PATH)
            logging.info("X/Twitter login successful and cookies saved.")
    except Exception as e:
        logging.error(f"Failed to log in to X/Twitter: {e}", exc_info=True)
        return [], None

    found_memes = []
    next_cursor = None

    try:
        logging.info(f"Searching X/Twitter for '{keyword}', sorted by 'Latest', with cursor: {after}")
        # Search by 'Latest' to get the most recent tweets first.
        # The 'after' parameter from our function is used as the 'cursor' for twikit.
        search_results = await client.search_tweet(keyword, 'Latest', cursor=after)

        for tweet in search_results:
            if len(found_memes) >= limit:
                break

            if tweet.media and any(media.type == 'photo' for media in tweet.media):
                for media in tweet.media:
                    if media.type == 'photo':
                        found_memes.append({
                            'id': tweet.id,
                            'title': tweet.text,
                            'url': media.media_url_https,
                            'score': tweet.favorite_count,
                            'thumbnail_url': media.media_url_https, # X doesn't have separate thumbnails
                            'source': 'x'
                        })
                        break # Use the first photo found in the tweet

        # After the loop, get the cursor for the next page of results.
        next_cursor = search_results.cursor
        logging.info(f"Next X/Twitter cursor: {next_cursor}")

    except Exception as e:
        logging.error(f"An error occurred during tweet search: {e}", exc_info=True)

    return found_memes, next_cursor

def fetch_x_memes(username: str, password: str, keyword: str, limit: int = 25, after: str | None = None):
    """
    Synchronous wrapper to fetch image-based memes from X/Twitter.
    """
    if not all([username, password]):
        logging.error("X/Twitter credentials are missing.")
        return [], None

    try:
        return asyncio.run(search_tweets_async(username, password, keyword, limit, after))
    except Exception as e:
        logging.error(f"Failed to run the async X fetcher: {e}")
        return [], None