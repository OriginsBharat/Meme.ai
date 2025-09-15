from moviepy.editor import vfx

TARGET_ASPECT_RATIO = 9 / 16

def crop_to_portrait(clip):
    """
    Crops a video clip to a 9:16 aspect ratio from the center.
    """
    original_w, original_h = clip.size

    # Calculate the new dimensions for cropping
    if original_w / original_h > TARGET_ASPECT_RATIO:
        # Original is wider than target -> crop width
        new_w = int(original_h * TARGET_ASPECT_RATIO)
        new_h = original_h
    else:
        # Original is taller than target -> crop height
        new_w = original_w
        new_h = int(original_w / TARGET_ASPECT_RATIO)

    return vfx.crop(clip, width=new_w, height=new_h, x_center=original_w/2, y_center=original_h/2)
