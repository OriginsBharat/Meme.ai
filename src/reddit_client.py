import praw
import logging
import random
from used_memes_manager import get_used_meme_ids

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# A list of popular meme-related subreddits to search in.
SUBREDDITS_TO_SEARCH = [
    "memes",
    "dankmemes",
    "wholesomememes",
    "me_irl",
    "funny"
]

# Supported image formats
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png']

def fetch_reddit_memes(client_id: str, client_secret: str, user_agent: str, keyword: str, limit: int = 25, after: str | None = None):
    """
    Fetches a paginated list of image-based memes from Reddit, sorted by new.
    """
    if not all([client_id, client_secret, user_agent]):
        logging.error("Reddit API credentials are missing.")
        return [], None

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except Exception as e:
        logging.error(f"Failed to initialize PRAW Reddit instance: {e}")
        return [], None

    found_memes = []
    processed_post_ids = set()
    used_ids = get_used_meme_ids()
    logging.info(f"Excluding {len(used_ids)} already used memes.")

    # PRAW's search uses 'after' for pagination, which is a post's fullname.
    search_params = {}
    if after:
        search_params['after'] = after

    logging.info(f"Searching Reddit for '{keyword}', sorted by 'new', after post: {after}")

    # Join subreddits for a single, more efficient search query
    subreddit_string = "+".join(SUBREDDITS_TO_SEARCH)
    last_post_fullname = None

    try:
        subreddit = reddit.subreddit(subreddit_string)
        # Fetch more than the limit to account for filtering
        for post in subreddit.search(keyword, sort="new", limit=limit * 2, params=search_params):
            if len(found_memes) >= limit:
                break # Stop once we have enough valid memes for this page.

            if post.id in processed_post_ids or post.id in used_ids:
                continue
            processed_post_ids.add(post.id)

            is_image = any(post.url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)
            if not is_image:
                continue

            found_memes.append({
                'id': post.id,
                'title': post.title,
                'url': post.url,
                'score': post.score,
                'thumbnail_url': post.thumbnail,
                'source': 'reddit'
            })
            last_post_fullname = post.fullname # Continually update to get the last valid post

    except Exception as e:
        logging.error(f"Could not search subreddits: {e}")

    # No longer shuffling, as chronological order is desired for pagination
    return found_memes, last_post_fullname