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
from utils import crop_to_portrait

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def compile_video(
    meme_data: list[dict],
    master_resolution: tuple,
    intro_path: str,
    outro_path: str,
    bg_video_path: str,
    bg_music_path: str,
    output_path: str
) -> str | None:
    """
    Compiles a final video from memes, audio, and other assets using a layer-based approach.
    """
    logging.info("Starting video compilation process (layer-based architecture).")

    # Keep track of all created clips to ensure they are closed
    all_clips_to_close = []
    try:
        # --- 1. Create all video and audio clips ---
        intro_clip = crop_to_portrait(VideoFileClip(intro_path))
        all_clips_to_close.append(intro_clip)

        meme_clips = []
        meme_audio_clips = []
        current_time = intro_clip.duration

        for meme_config in meme_data:
            image_path = meme_config.get('image_path')
            audio_path = meme_config.get('tts_audio_path')
            transform = meme_config.get("transform", {"scale": 1.0, "pos": (0, 0)})

            if not all([image_path, audio_path, os.path.exists(image_path), os.path.exists(audio_path)]):
                logging.warning(f"Skipping meme due to missing file: {meme_config.get('title')}")
                continue

            # Create audio clip to get duration
            tts_audio = AudioFileClip(audio_path)
            all_clips_to_close.append(tts_audio)

            clip_duration = tts_audio.duration + 0.75

            # Create image clip with user's transform
            with Image.open(image_path) as pil_img:
                scale = transform.get("scale", 1.0)
                new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
                resized_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                image_array = np.array(resized_img)

            img_clip = ImageClip(image_array, duration=clip_duration, transparent=True)
            img_clip = img_clip.set_position(transform.get("pos", (0,0)))
            img_clip = img_clip.set_start(current_time)
            all_clips_to_close.append(img_clip)
            meme_clips.append(img_clip)

            # Set start time for audio as well
            tts_audio = tts_audio.set_start(current_time)
            meme_audio_clips.append(tts_audio)

            current_time += clip_duration

        if not meme_clips:
            logging.error("No valid meme clips could be created. Aborting compilation.")
            return None

        outro_clip = crop_to_portrait(VideoFileClip(outro_path))
        outro_clip = outro_clip.set_start(current_time)
        all_clips_to_close.append(outro_clip)

        total_duration = current_time + outro_clip.duration

        # --- 2. Prepare Backgrounds for the total duration ---
        bg_video_clip = VideoFileClip(bg_video_path).without_audio()
        if bg_video_clip.duration < total_duration:
            bg_video_clip = bg_video_clip.loop(duration=total_duration)
        else:
            bg_video_clip = bg_video_clip.subclip(0, total_duration)
        bg_video_clip = crop_to_portrait(bg_video_clip)
        all_clips_to_close.append(bg_video_clip)

        bg_music_clip = AudioFileClip(bg_music_path).volumex(0.1)
        if bg_music_clip.duration < total_duration:
            bg_music_clip = bg_music_clip.loop(duration=total_duration)
        else:
            bg_music_clip = bg_music_clip.subclip(0, total_duration)
        all_clips_to_close.append(bg_music_clip)

        # --- 3. Composite Everything Together ---
        logging.info("Compositing all layers...")
        final_audio = CompositeAudioClip(meme_audio_clips + [bg_music_clip])

        # Layer clips: background is first (bottom), then intro, memes, and outro
        final_video = CompositeVideoClip(
            [bg_video_clip, intro_clip] + meme_clips + [outro_clip],
            size=master_resolution
        )
        final_video.audio = final_audio
        final_video = final_video.set_duration(total_duration)

        # --- 4. Write Final Video to File ---
        logging.info(f"Writing final video to {output_path}")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=24,
            threads=4,
            logger='bar',
            ffmpeg_params=['-pix_fmt', 'yuv420p'] # For maximum compatibility
        )
        logging.info("Video compilation completed successfully.")
        return output_path

    except Exception as e:
        logging.error(f"An unexpected error occurred during video compilation: {e}", exc_info=True)
        return None
    finally:
        # --- 5. Clean up all file handles ---
        logging.info("Closing all media file handles.")
        for clip in all_clips_to_close:
            try:
                if clip: clip.close()
            except Exception:
                pass

        import gc
        gc.collect()
