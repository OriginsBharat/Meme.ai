import logging
import asyncio
from twikit import Client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# A constant to store the cookie file path
COOKIE_FILE_PATH = 'x_cookies.json'

async def search_tweets_async(username, password, keyword, limit):
    """
    Asynchronous function to perform the tweet search.
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
        # If login fails, we cannot proceed.
        return []

    found_memes = []
    try:
        logging.info(f"Searching X/Twitter for tweets with keyword: '{keyword}'")
        search_results = await client.search_tweet(keyword, 'media')

        for tweet in search_results:
            if len(found_memes) >= limit:
                break

            # We are interested in tweets that have images.
            if tweet.media and any(media.type == 'photo' for media in tweet.media):
                for media in tweet.media:
                    if media.type == 'photo':
                        # Use the first photo found in the tweet.
                        found_memes.append({
                            'id': tweet.id,
                            'title': tweet.text, # Use tweet text as title
                            'url': media.media_url_https, # The direct URL to the image
                            'score': tweet.favorite_count # Use favorite count as a proxy for score
                        })
                        # Stop after finding the first image in a tweet to avoid duplicates.
                        break
    except Exception as e:
        logging.error(f"An error occurred during tweet search: {e}", exc_info=True)

    return found_memes

def fetch_x_memes(username: str, password: str, keyword: str, total_limit: int = 25):
    """
    Synchronous wrapper to fetch image-based memes from X/Twitter.
    """
    if not all([username, password]):
        logging.error("X/Twitter credentials are missing.")
        return []

    try:
        # Run the async function in a new event loop
        return asyncio.run(search_tweets_async(username, password, keyword, total_limit))
    except Exception as e:
        logging.error(f"Failed to run the async X fetcher: {e}")
        return []