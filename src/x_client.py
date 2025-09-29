import logging
import asyncio
from twikit import Client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# A constant to store the cookie file path
COOKIE_FILE_PATH = 'x_cookies.json'

async def search_tweets_async(username, password, keyword, limit, after=None):
    """
    Asynchronous function to perform the tweet search.
    'after' is included for signature consistency but is not used by twikit's search.
    """
    client = Client(language='en-US')

    try:
        logging.info("Attempting to log in to X/Twitter...")
        await client.login(
            auth_info_1=username,
            password=password,
            cookies_file=COOKIE_FILE_PATH
        )
        logging.info("X/Twitter login successful.")
    except Exception as e:
        logging.error(f"Failed to log in to X/Twitter: {e}", exc_info=True)
        return [], None

    found_memes = []
    # Note: twikit search doesn't have a native 'after' cursor.
    # It fetches a batch. Infinite scroll for X will be more like a "load more" button
    # that re-runs the search, relying on 'newest' sort order to get different results.
    # For now, we fetch one batch and return None for the cursor.

    try:
        logging.info(f"Searching X/Twitter for '{keyword}', sorted by 'Latest'")
        # Search by 'Latest' to get the most recent tweets first.
        search_results = await client.search_tweet(keyword, 'Latest')

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
    except Exception as e:
        logging.error(f"An error occurred during tweet search: {e}", exc_info=True)

    # Return None for the cursor, as twikit does not support it for search.
    return found_memes, None

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