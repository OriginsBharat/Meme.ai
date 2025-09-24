import logging
import os
import yt_dlp

def download_video(video_url: str, output_dir: str) -> str | None:
    """
    Downloads a video from a given URL to a specified directory using yt-dlp.
    It specifically aims to get the best quality MP4 format, which is ideal for
    later processing with MoviePy.

    Args:
        video_url (str): The URL of the video to download (e.g., a Reddit post URL).
        output_dir (str): The directory to save the downloaded video in.

    Returns:
        str | None: The full path to the downloaded video file, or None if download fails.
    """
    logging.info(f"Attempting to download video from URL: {video_url}")

    # Configure yt-dlp options
    ydl_opts = {
        # Download best quality mp4 video available or any other best quality if mp4 not available.
        # This is crucial for compatibility with MoviePy.
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        # Define the output template for the downloaded file.
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'quiet': True, # Suppress console output from yt-dlp.
        'merge_output_format': 'mp4', # Ensure the final merged file is mp4.
        'noprogress': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            # ydl.prepare_filename gives the expected path based on the template
            downloaded_path = ydl.prepare_filename(info_dict)

            # When merging formats, the final file extension might be different from the template's.
            # We explicitly check for the merged '.mp4' file.
            base, _ = os.path.splitext(downloaded_path)
            final_path = base + '.mp4'
            if os.path.exists(final_path):
                # If the merged file exists, that's our target
                logging.info(f"Successfully downloaded and merged video to: {final_path}")
                return final_path
            elif os.path.exists(downloaded_path):
                # If no merge happened, the original path is correct
                logging.info(f"Successfully downloaded video to: {downloaded_path}")
                return downloaded_path
            else:
                logging.error(f"yt-dlp reported success, but output file not found at {final_path} or {downloaded_path}")
                return None

    except Exception as e:
        logging.error(f"Failed to download video from {video_url}. Error: {e}", exc_info=True)
        return None
