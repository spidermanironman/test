#!/usr/bin/env python3
"""
Flowchart Image Processor
- Converts dark background to white
- Inverts text colors for proper contrast
- Enhances clarity and resolution
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import base64
import io
import sys

# The image data will be embedded here as base64
# This is the uploaded flowchart image
IMAGE_BASE64 = """
"""

def load_image_from_base64(b64_string):
    """Load image from base64 string"""
    img_data = base64.b64decode(b64_string)
    img = Image.open(io.BytesIO(img_data))
    return np.array(img)

def load_image_from_file(filepath):
    """Load image from file"""
    img = cv2.imread(filepath)
    if img is None:
        raise ValueError(f"Could not read image: {filepath}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

def smart_invert_flowchart(img_rgb):
    """
    Smart inversion that:
    1. Changes black background to white
    2. Inverts light text/lines to dark
    3. Preserves and adjusts colored elements for visibility on white
    """
    # Convert to different color spaces for analysis
    img_hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(img_hsv)
    
    # Create output image with white background
    result = np.full_like(img_rgb, 255)
    
    # Thresholds
    bg_threshold = 35  # Pixels with value below this are background
    light_threshold = 180  # Pixels with value above this are light elements
    saturation_threshold = 40  # Low saturation means grayscale
    
    # Masks
    bg_mask = v < bg_threshold
    light_gray_mask = (v > light_threshold) & (s < saturation_threshold)
    dark_gray_mask = (v >= bg_threshold) & (v < 150) & (s < saturation_threshold)
    colored_mask = (s >= saturation_threshold) & ~bg_mask
    
    # Light gray elements (text, lines) -> dark gray/black
    result[light_gray_mask] = [30, 30, 30]
    
    # Medium gray elements -> slightly darker
    gray_values = v[dark_gray_mask]
    for i in range(3):
        result[:,:,i][dark_gray_mask] = (255 - gray_values).astype(np.uint8)
    
    # For colored elements, we need to adjust them for white background
    # Keep the hue but increase saturation and adjust value for visibility
    
    # Orange/Yellow elements (commonly used for warnings/decisions)
    orange_mask = cv2.inRange(img_hsv, np.array([5, 80, 80]), np.array([30, 255, 255]))
    if np.any(orange_mask):
        # Darken orange slightly for white bg
        result[orange_mask > 0] = (img_rgb[orange_mask > 0] * 0.85).astype(np.uint8)
    
    # Blue elements (commonly used for processes)
    blue_mask = cv2.inRange(img_hsv, np.array([90, 50, 50]), np.array([130, 255, 255]))
    if np.any(blue_mask):
        # Make blue slightly more saturated/darker
        blue_adjusted = img_rgb[blue_mask > 0].astype(np.float32)
        blue_adjusted[:, 0] = blue_adjusted[:, 0] * 0.7  # Reduce R
        blue_adjusted[:, 1] = blue_adjusted[:, 1] * 0.7  # Reduce G
        blue_adjusted[:, 2] = np.minimum(blue_adjusted[:, 2] * 1.1, 255)  # Boost B slightly
        result[blue_mask > 0] = blue_adjusted.astype(np.uint8)
    
    # Purple/Magenta elements
    purple_mask = cv2.inRange(img_hsv, np.array([130, 50, 50]), np.array([170, 255, 255]))
    if np.any(purple_mask):
        # Darken purple for white bg
        result[purple_mask > 0] = (img_rgb[purple_mask > 0] * 0.75).astype(np.uint8)
    
    # Green elements (commonly used for success states)
    green_mask = cv2.inRange(img_hsv, np.array([35, 50, 50]), np.array([85, 255, 255]))
    if np.any(green_mask):
        # Darken green for white bg
        result[green_mask > 0] = (img_rgb[green_mask > 0] * 0.8).astype(np.uint8)
    
    # Red elements
    red_mask1 = cv2.inRange(img_hsv, np.array([0, 80, 80]), np.array([10, 255, 255]))
    red_mask2 = cv2.inRange(img_hsv, np.array([170, 80, 80]), np.array([180, 255, 255]))
    red_mask = red_mask1 | red_mask2
    if np.any(red_mask):
        result[red_mask > 0] = (img_rgb[red_mask > 0] * 0.85).astype(np.uint8)
    
    return result

def enhance_clarity(pil_img, upscale_factor=2):
    """
    Enhance image clarity:
    1. Upscale using LANCZOS interpolation
    2. Apply sharpening
    3. Enhance contrast
    """
    # Get original size
    orig_width, orig_height = pil_img.size
    
    # Upscale
    new_size = (orig_width * upscale_factor, orig_height * upscale_factor)
    img_upscaled = pil_img.resize(new_size, Image.LANCZOS)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(img_upscaled)
    img_sharp = enhancer.enhance(1.5)
    
    # Apply unsharp mask for better edge definition
    img_unsharp = img_sharp.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
    
    # Slight contrast enhancement
    enhancer_contrast = ImageEnhance.Contrast(img_unsharp)
    img_final = enhancer_contrast.enhance(1.1)
    
    return img_final, orig_width, orig_height, new_size[0], new_size[1]

def simple_invert(img_rgb):
    """Simple color inversion - inverts all colors"""
    return 255 - img_rgb

def process_image(input_source, output_prefix="flowchart"):
    """Main processing function"""
    
    # Load image
    if isinstance(input_source, str):
        if input_source.startswith("/") or input_source.startswith("."):
            # File path
            print(f"Loading image from file: {input_source}")
            img_rgb = load_image_from_file(input_source)
        else:
            # Base64 string
            print("Loading image from base64...")
            img_rgb = load_image_from_base64(input_source)
    else:
        img_rgb = input_source
    
    print(f"Image loaded: {img_rgb.shape[1]}x{img_rgb.shape[0]}")
    
    # Method 1: Simple inversion
    print("\n[Method 1] Simple color inversion...")
    inverted_simple = simple_invert(img_rgb)
    pil_simple = Image.fromarray(inverted_simple)
    pil_simple_enhanced, ow, oh, nw, nh = enhance_clarity(pil_simple)
    output_simple = f"{output_prefix}_inverted.png"
    pil_simple_enhanced.save(output_simple, quality=95)
    print(f"  Saved: {output_simple} ({nw}x{nh})")
    
    # Method 2: Smart inversion (preserves colors)
    print("\n[Method 2] Smart color inversion (preserves colored elements)...")
    inverted_smart = smart_invert_flowchart(img_rgb)
    pil_smart = Image.fromarray(inverted_smart)
    pil_smart_enhanced, ow, oh, nw, nh = enhance_clarity(pil_smart)
    output_smart = f"{output_prefix}_smart.png"
    pil_smart_enhanced.save(output_smart, quality=95)
    print(f"  Saved: {output_smart} ({nw}x{nh})")
    
    print("\n✓ Processing complete!")
    print(f"  Original size: {ow}x{oh}")
    print(f"  Enhanced size: {nw}x{nh} (2x upscaled)")
    
    return output_simple, output_smart

if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_prefix = sys.argv[2] if len(sys.argv) > 2 else "flowchart"
        process_image(input_file, output_prefix)
    else:
        print("Usage: python invert_flowchart.py <input_image> [output_prefix]")
        print("\nExample:")
        print("  python invert_flowchart.py input.png output")
        print("  This will create: output_inverted.png and output_smart.png")
