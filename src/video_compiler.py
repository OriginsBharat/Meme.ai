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

def crop_to_portrait(clip):
    """
    Crops a video clip to a 9:16 aspect ratio from the center.
    """
    original_w, original_h = clip.size
    target_w, target_h = VIDEO_RESOLUTION
    target_aspect = target_w / target_h # 9 / 16

    # Calculate the new dimensions for cropping
    if original_w / original_h > target_aspect:
        # Original is wider than target -> crop width
        new_w = int(original_h * target_aspect)
        new_h = original_h
    else:
        # Original is taller than target -> crop height
        new_w = original_w
        new_h = int(original_w / target_aspect)

    return vfx.crop(clip, width=new_w, height=new_h, x_center=original_w/2, y_center=original_h/2)

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

            # --- "Fit Inside" Scaling Logic for Memes ---
            with Image.open(image_path) as pil_img:
                img_w, img_h = pil_img.size
                container_w, container_h = VIDEO_RESOLUTION

                ratio = min(container_w / img_w, container_h / img_h) * 0.95 # Apply 95% padding
                new_size = (int(img_w * ratio), int(img_h * ratio))

                # Use the modern Resampling.LANCZOS for high-quality downscaling
                resized_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                image_array = np.array(resized_img)

            # Create the image clip from the resized image array, preserving transparency
            img_clip = ImageClip(image_array, duration=image_duration, transparent=True)
            img_clip = img_clip.set_audio(tts_audio_clip)

            meme_clips.append(img_clip)

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

        # Crop the background to the target 9:16 aspect ratio
        bg_video_clip = crop_to_portrait(bg_video_clip)

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
        final_segment = CompositeVideoClip([bg_video_clip, meme_segment.set_position('center')])
        final_segment.audio = combined_audio

        # --- 5. Add Intro and Outro ---
        logging.info("Adding intro and outro.")
        intro_clip = crop_to_portrait(VideoFileClip(intro_path))
        outro_clip = crop_to_portrait(VideoFileClip(outro_path))

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
