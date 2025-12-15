#!/usr/bin/env python3
"""
Image processing script to:
1. Change black background to white
2. Invert text colors for contrast
3. Improve image clarity/sharpness
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import sys

def process_flowchart_image(input_path, output_path):
    """
    Process the flowchart image:
    - Convert black background to white
    - Invert text/element colors for contrast
    - Enhance sharpness and clarity
    """
    # Read image
    img = cv2.imread(input_path)
    if img is None:
        print(f"Error: Could not read image from {input_path}")
        return False
    
    # Convert to RGB (OpenCV uses BGR)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Create a mask for the dark background
    # Convert to HSV for better color detection
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # The background is very dark (black), so we detect dark pixels
    # Low value means dark color
    lower_dark = np.array([0, 0, 0])
    upper_dark = np.array([180, 255, 50])  # Low value (V < 50) means dark
    
    # Create mask for dark background
    dark_mask = cv2.inRange(img_hsv, lower_dark, upper_dark)
    
    # Invert the entire image first
    img_inverted = cv2.bitwise_not(img_rgb)
    
    # For better results, let's use a smarter approach:
    # 1. Invert the image
    # 2. Adjust specific color channels if needed
    
    # Convert to PIL for enhancement
    pil_img = Image.fromarray(img_inverted)
    
    # Enhance sharpness
    enhancer_sharpness = ImageEnhance.Sharpness(pil_img)
    pil_img = enhancer_sharpness.enhance(1.5)  # Increase sharpness
    
    # Enhance contrast
    enhancer_contrast = ImageEnhance.Contrast(pil_img)
    pil_img = enhancer_contrast.enhance(1.2)  # Slight contrast boost
    
    # Apply unsharp mask for better clarity
    pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    
    # Upscale for better resolution (2x)
    width, height = pil_img.size
    new_size = (width * 2, height * 2)
    pil_img_upscaled = pil_img.resize(new_size, Image.LANCZOS)
    
    # Apply another round of sharpening after upscaling
    enhancer_sharpness2 = ImageEnhance.Sharpness(pil_img_upscaled)
    pil_img_upscaled = enhancer_sharpness2.enhance(1.3)
    
    # Save result
    pil_img_upscaled.save(output_path, quality=95)
    print(f"Processed image saved to: {output_path}")
    print(f"Original size: {width}x{height}")
    print(f"New size: {new_size[0]}x{new_size[1]}")
    
    return True


def process_with_color_preservation(input_path, output_path):
    """
    Alternative processing that preserves some colors while inverting background
    """
    img = cv2.imread(input_path)
    if img is None:
        print(f"Error: Could not read image from {input_path}")
        return False
    
    # Convert to RGB
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Create output image starting with white background
    result = np.full_like(img_rgb, 255)  # White background
    
    # Convert to HSV for color analysis
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Detect non-background pixels (anything not very dark)
    # Background is black, so value < 30 is background
    h, s, v = cv2.split(img_hsv)
    
    # Create masks for different elements
    # Background mask (very dark)
    bg_mask = v < 30
    
    # Light/white elements (high value, low saturation) - these become dark
    light_mask = (v > 200) & (s < 50)
    
    # Colored elements - preserve but adjust for white background
    colored_mask = ~bg_mask & ~light_mask
    
    # For light elements (text that was light), make them dark
    result[light_mask] = [40, 40, 40]  # Dark gray/black
    
    # For colored elements, we need to adjust them
    # Keep the hue but adjust saturation and value for visibility on white
    for i in range(3):
        # Where there are colored elements, invert them
        result[:,:,i][colored_mask] = 255 - img_rgb[:,:,i][colored_mask]
    
    # Special handling for specific colors in the flowchart
    # Orange/yellow boxes - keep them visible
    orange_lower = np.array([5, 100, 100])
    orange_upper = np.array([25, 255, 255])
    orange_mask = cv2.inRange(img_hsv, orange_lower, orange_upper)
    
    # Blue elements
    blue_lower = np.array([100, 50, 50])
    blue_upper = np.array([130, 255, 255])
    blue_mask = cv2.inRange(img_hsv, blue_lower, blue_upper)
    
    # Purple elements
    purple_lower = np.array([130, 50, 50])
    purple_upper = np.array([160, 255, 255])
    purple_mask = cv2.inRange(img_hsv, purple_lower, purple_upper)
    
    # Green elements
    green_lower = np.array([35, 50, 50])
    green_upper = np.array([85, 255, 255])
    green_mask = cv2.inRange(img_hsv, green_lower, green_upper)
    
    # Restore original colors but make them darker/more saturated for white bg
    for mask, darken_factor in [(orange_mask, 0.8), (blue_mask, 0.7), (purple_mask, 0.7), (green_mask, 0.7)]:
        if np.any(mask):
            for i in range(3):
                result[:,:,i][mask > 0] = (img_rgb[:,:,i][mask > 0] * darken_factor).astype(np.uint8)
    
    # Convert to PIL for enhancement
    pil_img = Image.fromarray(result)
    
    # Enhance sharpness
    enhancer_sharpness = ImageEnhance.Sharpness(pil_img)
    pil_img = enhancer_sharpness.enhance(1.5)
    
    # Enhance contrast
    enhancer_contrast = ImageEnhance.Contrast(pil_img)
    pil_img = enhancer_contrast.enhance(1.15)
    
    # Apply unsharp mask
    pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    
    # Upscale 2x with high-quality interpolation
    width, height = pil_img.size
    new_size = (width * 2, height * 2)
    pil_img_upscaled = pil_img.resize(new_size, Image.LANCZOS)
    
    # Final sharpening
    enhancer_sharpness2 = ImageEnhance.Sharpness(pil_img_upscaled)
    pil_img_upscaled = enhancer_sharpness2.enhance(1.2)
    
    # Save
    pil_img_upscaled.save(output_path, quality=95)
    print(f"Processed image saved to: {output_path}")
    print(f"Original size: {width}x{height}")
    print(f"New size: {new_size[0]}x{new_size[1]}")
    
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_image.py <input_image> [output_image]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "processed_output.png"
    
    print("Processing with simple inversion method...")
    process_flowchart_image(input_path, output_path.replace(".png", "_inverted.png"))
    
    print("\nProcessing with color preservation method...")
    process_with_color_preservation(input_path, output_path.replace(".png", "_preserved.png"))
    
    print("\nDone!")
