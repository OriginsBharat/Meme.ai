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

def fetch_reddit_memes(
    client_id: str,
    client_secret: str,
    user_agent: str,
    keyword: str,
    total_limit: int = 25,
    search_limit_per_subreddit: int = 50,
    upvote_threshold: int = 300,
    after: str | None = None,
    max_video_duration: int = 10
) -> tuple[list, str | None]:
    """
    Fetches image and video memes from Reddit, sorted by new, with pagination.

    Args:
        client_id (str): The Reddit API client ID.
        client_secret (str): The Reddit API client secret.
        user_agent (str): The user agent for the Reddit API client.
        keyword (str): The keyword to search for in meme subreddits.
        total_limit (int): The maximum number of memes to return in total.
        search_limit_per_subreddit (int): Max posts to check in each subreddit.
        upvote_threshold (int): Minimum number of upvotes a post must have.
        after (str | None): The Reddit post `fullname` to start the search after.
        max_video_duration (int): The maximum duration for video memes.

    Returns:
        tuple[list, str | None]: A tuple containing:
            - A list of media dictionaries (image or video).
            - The fullname of the last item found, for pagination.
    """
    if not all([client_id, client_secret, user_agent]):
        logging.error("Reddit API credentials are missing.")
        return [], None

    logging.info(f"Initializing Reddit client. Searching for '{keyword}', after: {after}")
    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        logging.info(f"Reddit client read-only status: {reddit.read_only}")
    except Exception as e:
        logging.error(f"Failed to initialize PRAW Reddit instance: {e}")
        return [], None

    found_media = []
    processed_post_ids = set()
    used_ids = get_used_meme_ids()
    logging.info(f"Excluding {len(used_ids)} already used memes.")

    last_media_fullname = None
    search_params = {}
    if after:
        search_params['after'] = after

    logging.info(f"Searching for up to {total_limit} new memes with keyword '{keyword}'...")
    for subreddit_name in SUBREDDITS_TO_SEARCH:
        if len(found_media) >= total_limit:
            break
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.search(keyword, sort="new", limit=search_limit_per_subreddit, params=search_params):
                if len(found_media) >= total_limit:
                    break
                if post.id in processed_post_ids or post.id in used_ids:
                    continue
                processed_post_ids.add(post.id)

                if post.score < upvote_threshold:
                    continue

                media_data = None
                is_image = any(post.url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)

                if is_image:
                    media_data = {
                        'type': 'image',
                        'id': post.id, 'title': post.title, 'url': post.url,
                        'score': post.score, 'fullname': post.fullname
                    }
                elif post.is_video:
                    duration = post.media['reddit_video']['duration']
                    if duration <= max_video_duration:
                        media_data = {
                            'type': 'video',
                            'id': post.id, 'title': post.title, 'url': 'https://www.reddit.com' + post.permalink,
                            'score': post.score, 'fullname': post.fullname,
                            'duration': duration
                        }

                if media_data:
                    logging.info(f"Found suitable {media_data['type']}: '{media_data['title']}' (Score: {media_data['score']})")
                    found_media.append(media_data)

        except Exception as e:
            logging.error(f"Could not search subreddit r/{subreddit_name}: {e}")
            continue

    if found_media:
        last_media_fullname = found_media[-1]['fullname']

    logging.info(f"Found {len(found_media)} items. Last ID for pagination: {last_media_fullname}")
    return found_media, last_media_fullname
