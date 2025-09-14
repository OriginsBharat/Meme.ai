import logging
import os
import numpy as np
from PIL import Image
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    concatenate_videoclips,
    CompositeAudioClip,
    ColorClip
)
import moviepy.video.fx.all as vfx

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Standard video resolution
VIDEO_RESOLUTION = (1080, 1920) # Portrait mode for shorts/reels

def resize_frame_for_portrait(frame):
    """
    A function to resize a single video frame to fit the portrait resolution.
    This is a substitute for the buggy moviepy.resize function.
    """
    pil_img = Image.fromarray(frame)
    resized_pil = pil_img.resize(VIDEO_RESOLUTION, Image.Resampling.LANCZOS)
    return np.array(resized_pil)

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

    audio_clips = []
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
            audio_clips.append(tts_audio_clip)
            # Per user request, duration is TTS length + 0.75s
            image_duration = tts_audio_clip.duration + 0.75

            # --- Manual Image Resizing using Pillow ---
            with Image.open(image_path) as pil_img:
                # Convert RGBA to RGB if necessary (moviepy can have issues with alpha channels)
                if pil_img.mode == 'RGBA':
                    pil_img = pil_img.convert('RGB')

                # --- "Fit Inside" Scaling Logic ---
                img_w, img_h = pil_img.size
                container_w, container_h = VIDEO_RESOLUTION

                # Calculate the scaling ratio to fit inside the container
                ratio_w = container_w / img_w
                ratio_h = container_h / img_h
                scale_ratio = min(ratio_w, ratio_h)

                new_w = int(img_w * scale_ratio)
                new_h = int(img_h * scale_ratio)

                # Use the modern Resampling.LANCZOS for high-quality downscaling
                resized_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # Convert the Pillow image to a NumPy array for ImageClip
                image_array = np.array(resized_img)

            # Create the image clip from the resized image array
            img_clip = ImageClip(image_array, duration=image_duration)

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

        # Resize background to standard resolution using our custom function
        bg_video_clip = bg_video_clip.fl_image(resize_frame_for_portrait)

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
        intro_clip = VideoFileClip(intro_path)
        outro_clip = VideoFileClip(outro_path)

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
        # --- 7. Clean up all file handles ---
        logging.info("Closing all audio and video file handles.")
        for clip in meme_clips:
            if clip: clip.close()
        for clip in audio_clips:
            if clip: clip.close()
        if 'bg_video_clip' in locals() and bg_video_clip: bg_video_clip.close()
        if 'bg_music_clip' in locals() and bg_music_clip: bg_music_clip.close()
        if 'intro_clip' in locals() and intro_clip: intro_clip.close()
        if 'outro_clip' in locals() and outro_clip: outro_clip.close()

        # Clean up moviepy's internal state if needed
        import gc
        gc.collect()
