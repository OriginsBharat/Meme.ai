import logging
import os
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    concatenate_videoclips,
    CompositeAudioClip,
    ColorClip
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Standard video resolution
VIDEO_RESOLUTION = (1080, 1920) # Portrait mode for shorts/reels

def compile_video(
    meme_data: list[dict],
    intro_path: str,
    outro_path: str,
    bg_video_path: str,
    bg_music_path: str,
    output_path: str
) -> str | None:
    """
    Compiles a final video from memes, audio, and other assets.

    Args:
        meme_data (list[dict]): A list of dictionaries, each containing 'image_path'
                                and 'tts_audio_path' for a meme.
        intro_path (str): Path to the intro video file.
        outro_path (str): Path to the outro video file.
        bg_video_path (str): Path to the background gameplay video file.
        bg_music_path (str): Path to the background music audio file.
        output_path (str): The destination path for the final compiled video.

    Returns:
        str | None: The path to the final video if successful, otherwise None.
    """
    logging.info("Starting video compilation process.")

    try:
        # --- 1. Create Clips for Each Meme ---
        meme_clips = []
        for meme in meme_data:
            image_path = meme.get('image_path')
            audio_path = meme.get('tts_audio_path')

            if not all([image_path, audio_path, os.path.exists(image_path), os.path.exists(audio_path)]):
                logging.warning(f"Skipping meme due to missing file: image='{image_path}', audio='{audio_path}'")
                continue

            logging.info(f"Processing meme: {os.path.basename(image_path)}")

            # Load the TTS audio to determine its duration
            tts_audio_clip = AudioFileClip(audio_path)
            # Per user request, duration is TTS length + 0.75s
            image_duration = tts_audio_clip.duration + 0.75

            # Create the image clip
            img_clip = ImageClip(image_path, duration=image_duration)

            # Resize image to fit width of standard resolution, maintaining aspect ratio
            img_clip = img_clip.resize(width=VIDEO_RESOLUTION[0])

            # Create a background color clip
            bg_clip = ColorClip(size=VIDEO_RESOLUTION, color=(0,0,0), duration=image_duration)

            # Center the image on the background
            img_clip = img_clip.set_position('center')

            # Composite the image on top of the black background
            final_meme_clip = CompositeVideoClip([bg_clip, img_clip])
            final_meme_clip = final_meme_clip.set_audio(tts_audio_clip)

            meme_clips.append(final_meme_clip)

        if not meme_clips:
            logging.error("No valid meme clips could be created. Aborting compilation.")
            return None

        # --- 2. Concatenate Meme Clips into a Single Segment ---
        logging.info("Concatenating individual meme clips.")
        meme_segment = concatenate_videoclips(meme_clips)
        meme_segment_duration = meme_segment.duration

        # --- 3. Prepare Backgrounds ---
        logging.info("Preparing background video and music.")
        # Load background video and trim/loop to match meme segment duration
        bg_video_clip = VideoFileClip(bg_video_path).without_audio()
        if bg_video_clip.duration > meme_segment_duration:
            bg_video_clip = bg_video_clip.subclip(0, meme_segment_duration)
        else:
            bg_video_clip = bg_video_clip.loop(duration=meme_segment_duration)

        # Resize background to standard resolution
        bg_video_clip = bg_video_clip.resize(VIDEO_RESOLUTION)

        # Load background music and trim/loop
        bg_music_clip = AudioFileClip(bg_music_path)
        if bg_music_clip.duration > meme_segment_duration:
            bg_music_clip = bg_music_clip.subclip(0, meme_segment_duration)
        else:
            bg_music_clip = bg_music_clip.loop(duration=meme_segment_duration)
        # Lower the volume of background music to not overpower TTS
        bg_music_clip = bg_music_clip.volumex(0.2)

        # --- 4. Composite Meme Segment with Backgrounds ---
        logging.info("Compositing meme segment with backgrounds.")
        # Combine the TTS audio from the meme segment with the background music
        combined_audio = CompositeAudioClip([meme_segment.audio, bg_music_clip])

        # Place the meme segment on top of the background video
        final_segment = CompositeVideoClip([bg_video_clip, meme_segment])
        final_segment.audio = combined_audio

        # --- 5. Add Intro and Outro ---
        logging.info("Adding intro and outro.")
        intro_clip = VideoFileClip(intro_path).resize(VIDEO_RESOLUTION)
        outro_clip = VideoFileClip(outro_path).resize(VIDEO_RESOLUTION)

        final_video = concatenate_videoclips([intro_clip, final_segment, outro_clip])

        # --- 6. Write Final Video to File ---
        logging.info(f"Writing final video to {output_path}")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=24,
            threads=4, # Use multiple threads for faster writing
            logger='bar' # Show a progress bar
        )
        logging.info("Video compilation completed successfully.")
        return output_path

    except Exception as e:
        logging.error(f"An unexpected error occurred during video compilation: {e}", exc_info=True)
        return None
    finally:
        # Clean up moviepy's internal state if needed
        import gc
        gc.collect()
