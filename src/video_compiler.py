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

    if original_w / original_h > target_aspect:
        new_w = int(original_h * target_aspect)
        new_h = original_h
    else:
        new_w = original_w
        new_h = int(original_w / target_aspect)

    return vfx.crop(clip, width=new_w, height=new_h, x_center=original_w/2, y_center=original_h/2)

def resize_frame_for_portrait(frame):
    """
    A function to resize a single video frame to the final 1080x1920 resolution.
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
    Compiles a final video from memes, audio, and other assets using a layer-based approach.
    """
    logging.info("Starting video compilation process (layer-based architecture).")

    # Keep track of all created clips to ensure they are closed
    all_clips_to_close = []
    try:
        # --- 1. Create all video and audio clips ---
        intro_clip = crop_to_portrait(VideoFileClip(intro_path))
        intro_clip = intro_clip.fl_image(resize_frame_for_portrait)
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
        outro_clip = outro_clip.fl_image(resize_frame_for_portrait)
        outro_clip = outro_clip.set_start(current_time)
        all_clips_to_close.append(outro_clip)

        total_duration = current_time + outro_clip.duration

        # --- 2. Prepare Backgrounds and Main Audio Track ---
        bg_video_clip = VideoFileClip(bg_video_path).without_audio()
        if bg_video_clip.duration < total_duration:
            bg_video_clip = bg_video_clip.loop(duration=total_duration)
        else:
            bg_video_clip = bg_video_clip.subclip(0, total_duration)
        bg_video_clip = crop_to_portrait(bg_video_clip)
        bg_video_clip = bg_video_clip.fl_image(resize_frame_for_portrait)
        all_clips_to_close.append(bg_video_clip)

        # Prepare background music to start playing *after* the intro finishes.
        bg_music_clip = AudioFileClip(bg_music_path).volumex(0.1)
        intro_duration = intro_clip.duration

        # The background music should run from the end of the intro to the end of the video.
        bg_music_needed_duration = total_duration - intro_duration

        if bg_music_needed_duration > 0:
            if bg_music_clip.duration < bg_music_needed_duration:
                bg_music_clip = bg_music_clip.loop(duration=bg_music_needed_duration)
            else:
                bg_music_clip = bg_music_clip.subclip(0, bg_music_needed_duration)

            bg_music_clip = bg_music_clip.set_start(intro_duration)
            all_clips_to_close.append(bg_music_clip)

        # --- 3. Composite Everything Together ---
        logging.info("Compositing all layers...")

        # Explicitly get audio from intro and outro clips.
        # The .audio attribute of a transformed clip (e.g., set_start) is also transformed.
        intro_audio = intro_clip.audio
        outro_audio = outro_clip.audio
        all_clips_to_close.extend([intro_audio, outro_audio])

        # Combine all audio sources: the main track (intro, memes, outro) and the background music.
        audio_sources = [intro_audio, outro_audio] + meme_audio_clips
        if bg_music_needed_duration > 0:
            audio_sources.append(bg_music_clip)

        final_audio = CompositeAudioClip(audio_sources)

        # Layer clips: background is first (bottom), then intro, memes, and outro
        final_video = CompositeVideoClip(
            [bg_video_clip, intro_clip] + meme_clips + [outro_clip],
            size=VIDEO_RESOLUTION
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
