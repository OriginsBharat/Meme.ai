import praw
import logging
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

def fetch_reddit_memes(client_id: str, client_secret: str, user_agent: str, keyword: str, total_limit: int = 25, search_limit_per_subreddit: int = 50, upvote_threshold: int = 500, comment_threshold: int = 2):
    """
    Fetches image-based memes from Reddit based on a keyword and specific criteria.

    Args:
        client_id (str): The Reddit API client ID.
        client_secret (str): The Reddit API client secret.
        user_agent (str): The user agent for the Reddit API client.
        keyword (str): The keyword to search for in meme subreddits.
        total_limit (int): The maximum number of memes to return in total.
        search_limit_per_subreddit (int): The max number of posts to check in each subreddit.
        upvote_threshold (int): The minimum number of upvotes a post must have.
        comment_threshold (int): The minimum number of comments containing "relatable".

    Returns:
        list: A list of dictionaries, where each dictionary represents a meme
              that meets the criteria. Each dictionary contains the post's
              ID, title, URL, and score.
    """
    if not all([client_id, client_secret, user_agent]):
        logging.error("Reddit API credentials (client_id, client_secret, user_agent) are missing.")
        return []

    logging.info(f"Initializing Reddit client with user agent: {user_agent}")
    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        # Verify that the connection is read-only and credentials are valid
        logging.info(f"Reddit client read-only status: {reddit.read_only}")
    except Exception as e:
        logging.error(f"Failed to initialize PRAW Reddit instance: {e}")
        return []

    found_memes = []
    # Use a set to avoid processing duplicate posts if they appear in multiple searches
    processed_post_ids = set()
    used_ids = get_used_meme_ids()
    logging.info(f"Found {len(used_ids)} already used memes. They will be excluded from the search.")

    logging.info(f"Searching for up to {total_limit} memes with keyword '{keyword}'...")
    for subreddit_name in SUBREDDITS_TO_SEARCH:
        if len(found_memes) >= total_limit:
            logging.info("Total meme limit reached. Stopping search.")
            break
        try:
            subreddit = reddit.subreddit(subreddit_name)
            # Search for posts within the subreddit
            for post in subreddit.search(keyword, sort="relevance", limit=search_limit_per_subreddit):
                if post.id in processed_post_ids or post.id in used_ids:
                    continue
                processed_post_ids.add(post.id)

                if len(found_memes) >= total_limit:
                    break

                # --- Filtering Criteria ---
                # 1. Check if the post URL ends with a supported image extension
                is_image = any(post.url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)
                if not is_image:
                    continue

                # 2. Check if the score is above the threshold
                if post.score < upvote_threshold:
                    continue

                # 3. Check for "relatable" comments (this is the most intensive check)
                relatable_comment_count = 0
                post.comments.replace_more(limit=0)  # Remove "MoreComments" objects
                for comment in post.comments.list():
                    if 'relatable' in comment.body.lower():
                        relatable_comment_count += 1
                    if relatable_comment_count >= comment_threshold:
                        break  # Stop counting once the threshold is met

                if relatable_comment_count >= comment_threshold:
                    logging.info(f"Found suitable meme: '{post.title}' from r/{subreddit_name} with score {post.score}")
                    found_memes.append({
                        'id': post.id,
                        'title': post.title,
                        'url': post.url,
                        'score': post.score
                    })
        except Exception as e:
            logging.error(f"Could not search subreddit r/{subreddit_name}: {e}")
            continue

    logging.info(f"Found a total of {len(found_memes)} memes matching the criteria.")
    return found_memes[:total_limit]
