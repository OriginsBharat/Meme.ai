import logging
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# The file to store the user's access and refresh tokens.
TOKEN_PICKLE_FILE = 'token.pickle'

# The scopes define the level of access you are requesting.
SCOPES = ['https://www.googleapis.com/auth/upload.video']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

def get_authenticated_service(client_secrets_file):
    """
    Authenticates the user and returns a YouTube service object.
    Handles the OAuth 2.0 flow, including token storage and refresh.
    """
    credentials = None

    # Check if we have stored credentials
    if os.path.exists(TOKEN_PICKLE_FILE):
        with open(TOKEN_PICKLE_FILE, 'rb') as token:
            credentials = pickle.load(token)

    # If there are no valid credentials available, let the user log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not os.path.exists(client_secrets_file):
                raise FileNotFoundError(f"Client secrets file not found at {client_secrets_file}. Please configure it in Settings.")
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
            # This will open a browser window for the user to authorize the app
            credentials = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(TOKEN_PICKLE_FILE, 'wb') as token:
            pickle.dump(credentials, token)

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

def upload_video(client_secrets_file: str, video_path: str, title: str, description: str, tags: list[str]) -> str | None:
    """
    Uploads a video to YouTube.

    Args:
        client_secrets_file (str): Path to the Google Cloud client secrets JSON file.
        video_path (str): Path to the video file to upload.
        title (str): The title of the video.
        description (str): The description of the video.
        tags (list[str]): A list of tags for the video.

    Returns:
        str | None: The ID of the uploaded video, or None if it failed.
    """
    try:
        logging.info("Attempting to authenticate with Google...")
        youtube = get_authenticated_service(client_secrets_file)
        logging.info("Authentication successful. Starting upload.")

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': '24' # Entertainment category
            },
            'status': {
                'privacyStatus': 'private' # Upload as private first
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)

        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logging.info(f"Uploaded {int(status.progress() * 100)}%.")

        logging.info(f"Upload successful! Video ID: {response.get('id')}")
        return response.get('id')

    except Exception as e:
        logging.error(f"An error occurred during YouTube upload: {e}", exc_info=True)
        return None
