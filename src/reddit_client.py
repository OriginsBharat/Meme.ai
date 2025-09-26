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

def fetch_reddit_memes(client_id: str, client_secret: str, user_agent: str, keyword: str, total_limit: int = 25, search_limit_per_subreddit: int = 50, upvote_threshold: int = 500):
    """
    Fetches image-based memes from Reddit based on a keyword and specific criteria.
    """
    if not all([client_id, client_secret, user_agent]):
        logging.error("Reddit API credentials are missing.")
        return []

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except Exception as e:
        logging.error(f"Failed to initialize PRAW Reddit instance: {e}")
        return []

    found_memes = []
    processed_post_ids = set()
    used_ids = get_used_meme_ids()
    logging.info(f"Excluding {len(used_ids)} already used memes.")

    logging.info(f"Searching for up to {total_limit} memes with keyword '{keyword}'...")
    for subreddit_name in SUBREDDITS_TO_SEARCH:
        if len(found_memes) >= total_limit:
            break
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.search(keyword, sort="relevance", limit=search_limit_per_subreddit):
                if post.id in processed_post_ids or post.id in used_ids:
                    continue
                processed_post_ids.add(post.id)

                if len(found_memes) >= total_limit:
                    break

                if post.score < upvote_threshold:
                    continue

                is_image = any(post.url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)
                if not is_image:
                    continue

                found_memes.append({
                    'id': post.id,
                    'title': post.title,
                    'url': post.url,
                    'score': post.score
                })
        except Exception as e:
            logging.error(f"Could not search subreddit r/{subreddit_name}: {e}")
            continue

    random.shuffle(found_memes)
    return found_memes[:total_limit]