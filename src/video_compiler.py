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
    Compiles a final video from a mix of image and video memes.
    """
    logging.info("Starting mixed-media video compilation process.")

    all_clips_to_close = []
    try:
        # --- 1. Process main clips and timeline ---
        intro_clip = crop_to_portrait(VideoFileClip(intro_path))
        intro_clip = intro_clip.fl_image(resize_frame_for_portrait)

        # Lists to hold all our visual and audio components
        visual_clips = [intro_clip]
        audio_clips = [intro_clip.audio]
        all_clips_to_close.extend([intro_clip, intro_clip.audio])

        current_time = intro_clip.duration

        for config in meme_data:
            transform = config.get("transform", {"scale": 1.0, "pos": (0, 0)})
            media_type = config.get('type')

            clip_duration = 0

            if media_type == 'image':
                image_path = config.get('image_path')
                audio_path = config.get('tts_audio_path')
                if not all([image_path, os.path.exists(image_path)]):
                    logging.warning(f"Skipping image meme '{config['title']}' due to missing file.")
                    continue

                # Create audio clip to get duration, if TTS exists
                if audio_path and os.path.exists(audio_path):
                    tts_audio = AudioFileClip(audio_path)
                    clip_duration = tts_audio.duration + 0.75
                    tts_audio = tts_audio.set_start(current_time)
                    audio_clips.append(tts_audio)
                    all_clips_to_close.append(tts_audio)
                else:
                    # If no text, default duration for the image
                    clip_duration = 3.0

                with Image.open(image_path) as pil_img:
                    scale = transform.get("scale", 1.0)
                    new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
                    resized_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
                    image_array = np.array(resized_img)

                img_clip = ImageClip(image_array, duration=clip_duration).set_start(current_time).set_position(transform.get("pos", "center"))
                visual_clips.append(img_clip)
                all_clips_to_close.append(img_clip)

            elif media_type == 'video':
                video_path = config.get('video_path')
                if not all([video_path, os.path.exists(video_path)]):
                    logging.warning(f"Skipping video meme '{config['title']}' due to missing file.")
                    continue

                video_clip = crop_to_portrait(VideoFileClip(video_path))
                clip_duration = video_clip.duration

                # Apply scale transform by resizing each frame manually to avoid moviepy's buggy internal resize
                scale = transform.get("scale", 1.0)
                new_size = (int(video_clip.w * scale), int(video_clip.h * scale))

                # Use a lambda with fl_image to apply a high-quality resize to each frame
                video_clip = video_clip.fl_image(lambda frame: np.array(Image.fromarray(frame).resize(new_size, Image.Resampling.LANCZOS)))

                video_clip = video_clip.set_start(current_time).set_position(transform.get("pos", "center"))

                visual_clips.append(video_clip)
                audio_clips.append(video_clip.audio.set_start(current_time))
                all_clips_to_close.extend([video_clip, video_clip.audio])

            current_time += clip_duration

        # --- 2. Add Outro ---
        outro_clip = crop_to_portrait(VideoFileClip(outro_path))
        outro_clip = outro_clip.fl_image(resize_frame_for_portrait)
        outro_clip = outro_clip.set_start(current_time)
        visual_clips.append(outro_clip)
        audio_clips.append(outro_clip.audio.set_start(current_time))
        all_clips_to_close.extend([outro_clip, outro_clip.audio])

        total_duration = current_time + outro_clip.duration

        # --- 3. Prepare Backgrounds ---
        bg_video_clip = VideoFileClip(bg_video_path).without_audio()
        if bg_video_clip.duration < total_duration:
            bg_video_clip = bg_video_clip.loop(duration=total_duration)
        else:
            bg_video_clip = bg_video_clip.subclip(0, total_duration)
        bg_video_clip = crop_to_portrait(bg_video_clip).fl_image(resize_frame_for_portrait)
        all_clips_to_close.append(bg_video_clip)

        bg_music_clip = AudioFileClip(bg_music_path).volumex(0.1)
        bg_music_needed_duration = total_duration - intro_clip.duration
        if bg_music_needed_duration > 0:
            if bg_music_clip.duration < bg_music_needed_duration:
                bg_music_clip = bg_music_clip.loop(duration=bg_music_needed_duration)
            else:
                bg_music_clip = bg_music_clip.subclip(0, bg_music_needed_duration)
            bg_music_clip = bg_music_clip.set_start(intro_clip.duration)
            audio_clips.append(bg_music_clip)
            all_clips_to_close.append(bg_music_clip)

        # --- 4. Composite Everything ---
        logging.info("Compositing all audio and video layers...")
        final_audio = CompositeAudioClip(audio_clips)

        final_video = CompositeVideoClip([bg_video_clip] + visual_clips, size=VIDEO_RESOLUTION)
        final_video.audio = final_audio
        final_video = final_video.set_duration(total_duration)

        # --- 5. Write Final Video ---
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
