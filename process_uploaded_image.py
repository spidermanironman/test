#!/usr/bin/env python3
"""
完整的流程图图片处理器
- 将黑色背景变成白色
- 将文字变成对比色（深色）
- 提高清晰度
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import sys
import os

def process_flowchart(input_path, output_path):
    """
    处理流程图图片：
    1. 黑色背景 -> 白色背景
    2. 浅色文字 -> 深色文字
    3. 保留彩色元素但调整为适合白色背景
    4. 提高清晰度和分辨率
    """
    print(f"正在加载图片: {input_path}")
    
    # 使用OpenCV读取图片
    img = cv2.imread(input_path)
    if img is None:
        print(f"错误：无法读取图片 {input_path}")
        return False
    
    # 转换为RGB格式
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    print(f"原始尺寸: {img_rgb.shape[1]}x{img_rgb.shape[0]}")
    
    # 转换为HSV以进行颜色分析
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(img_hsv)
    
    # 创建输出图片（白色背景）
    result = np.full_like(img_rgb, 255, dtype=np.uint8)
    
    # === 第1步：识别并处理不同区域 ===
    
    # 背景阈值（值<35视为黑色背景）
    bg_threshold = 35
    bg_mask = v < bg_threshold
    
    # 灰度元素（低饱和度）
    gray_mask = s < 50
    
    # 浅灰/白色元素（文字、线条）
    light_mask = (v > 150) & gray_mask
    # 中间灰度元素
    mid_gray_mask = (v >= bg_threshold) & (v <= 150) & gray_mask
    
    # 彩色元素
    colored_mask = (s >= 50) & ~bg_mask
    
    # === 第2步：处理灰度元素 ===
    
    # 浅色文字/线条 -> 深色
    result[light_mask] = [40, 40, 40]  # 深灰色
    
    # 中间灰度元素 -> 反转
    mid_values = v[mid_gray_mask]
    inverted_values = 255 - mid_values
    for i in range(3):
        result[:,:,i][mid_gray_mask] = inverted_values
    
    # === 第3步：处理彩色元素 ===
    
    # 橙色/黄色元素（决策框）
    orange_lower = np.array([5, 80, 80])
    orange_upper = np.array([30, 255, 255])
    orange_mask = cv2.inRange(img_hsv, orange_lower, orange_upper)
    if np.any(orange_mask):
        # 稍微加深橙色以适应白色背景
        orange_pixels = img_rgb[orange_mask > 0].astype(float)
        orange_pixels = np.clip(orange_pixels * 0.85, 0, 255)
        result[orange_mask > 0] = orange_pixels.astype(np.uint8)
    
    # 蓝色元素（流程框）
    blue_lower = np.array([90, 40, 40])
    blue_upper = np.array([130, 255, 255])
    blue_mask = cv2.inRange(img_hsv, blue_lower, blue_upper)
    if np.any(blue_mask):
        blue_pixels = img_rgb[blue_mask > 0].astype(float)
        # 调整蓝色使其更深
        blue_pixels[:, 0] *= 0.6  # 降低红色
        blue_pixels[:, 1] *= 0.6  # 降低绿色
        blue_pixels[:, 2] = np.minimum(blue_pixels[:, 2] * 1.1, 255)  # 保持蓝色
        result[blue_mask > 0] = np.clip(blue_pixels, 0, 255).astype(np.uint8)
    
    # 紫色元素
    purple_lower = np.array([130, 40, 40])
    purple_upper = np.array([170, 255, 255])
    purple_mask = cv2.inRange(img_hsv, purple_lower, purple_upper)
    if np.any(purple_mask):
        purple_pixels = img_rgb[purple_mask > 0].astype(float)
        purple_pixels = np.clip(purple_pixels * 0.75, 0, 255)
        result[purple_mask > 0] = purple_pixels.astype(np.uint8)
    
    # 绿色元素（完成状态）
    green_lower = np.array([35, 40, 40])
    green_upper = np.array([85, 255, 255])
    green_mask = cv2.inRange(img_hsv, green_lower, green_upper)
    if np.any(green_mask):
        green_pixels = img_rgb[green_mask > 0].astype(float)
        green_pixels = np.clip(green_pixels * 0.75, 0, 255)
        result[green_mask > 0] = green_pixels.astype(np.uint8)
    
    # 红色元素（错误/警告）
    red_lower1 = np.array([0, 80, 80])
    red_upper1 = np.array([10, 255, 255])
    red_lower2 = np.array([170, 80, 80])
    red_upper2 = np.array([180, 255, 255])
    red_mask1 = cv2.inRange(img_hsv, red_lower1, red_upper1)
    red_mask2 = cv2.inRange(img_hsv, red_lower2, red_upper2)
    red_mask = red_mask1 | red_mask2
    if np.any(red_mask):
        red_pixels = img_rgb[red_mask > 0].astype(float)
        red_pixels = np.clip(red_pixels * 0.85, 0, 255)
        result[red_mask > 0] = red_pixels.astype(np.uint8)
    
    # === 第4步：转换为PIL并增强 ===
    pil_img = Image.fromarray(result)
    
    # 锐化增强
    enhancer_sharp = ImageEnhance.Sharpness(pil_img)
    pil_img = enhancer_sharp.enhance(1.4)
    
    # 对比度微调
    enhancer_contrast = ImageEnhance.Contrast(pil_img)
    pil_img = enhancer_contrast.enhance(1.1)
    
    # 应用USM锐化
    pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=100, threshold=2))
    
    # === 第5步：提高分辨率（2倍放大） ===
    orig_w, orig_h = pil_img.size
    new_w, new_h = orig_w * 2, orig_h * 2
    
    pil_img_upscaled = pil_img.resize((new_w, new_h), Image.LANCZOS)
    
    # 放大后再次锐化
    enhancer_sharp2 = ImageEnhance.Sharpness(pil_img_upscaled)
    pil_img_upscaled = enhancer_sharp2.enhance(1.2)
    
    # 保存结果
    pil_img_upscaled.save(output_path, quality=95, dpi=(300, 300))
    
    print(f"✓ 处理完成!")
    print(f"  新尺寸: {new_w}x{new_h} (2倍放大)")
    print(f"  输出文件: {output_path}")
    
    return True


def simple_invert(input_path, output_path):
    """简单反转方法：直接反转所有颜色"""
    print(f"正在使用简单反转方法处理: {input_path}")
    
    img = cv2.imread(input_path)
    if img is None:
        print(f"错误：无法读取图片 {input_path}")
        return False
    
    # 反转颜色
    img_inverted = 255 - img
    
    # 转换为PIL
    img_rgb = cv2.cvtColor(img_inverted, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    
    # 增强
    enhancer_sharp = ImageEnhance.Sharpness(pil_img)
    pil_img = enhancer_sharp.enhance(1.4)
    
    enhancer_contrast = ImageEnhance.Contrast(pil_img)
    pil_img = enhancer_contrast.enhance(1.15)
    
    pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
    
    # 2倍放大
    orig_w, orig_h = pil_img.size
    new_w, new_h = orig_w * 2, orig_h * 2
    pil_img_upscaled = pil_img.resize((new_w, new_h), Image.LANCZOS)
    
    enhancer_sharp2 = ImageEnhance.Sharpness(pil_img_upscaled)
    pil_img_upscaled = enhancer_sharp2.enhance(1.2)
    
    pil_img_upscaled.save(output_path, quality=95, dpi=(300, 300))
    
    print(f"✓ 简单反转完成!")
    print(f"  新尺寸: {new_w}x{new_h}")
    print(f"  输出文件: {output_path}")
    
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python process_uploaded_image.py <输入图片> [输出目录]")
        print("\n示例:")
        print("  python process_uploaded_image.py input.png")
        print("  python process_uploaded_image.py input.png /output/dir")
        print("\n将生成两个版本:")
        print("  - *_smart.png  : 智能处理（保留彩色元素）")
        print("  - *_simple.png : 简单反转")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(input_path) or "."
    
    # 获取文件名（不含扩展名）
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    
    # 生成输出路径
    smart_output = os.path.join(output_dir, f"{base_name}_smart.png")
    simple_output = os.path.join(output_dir, f"{base_name}_simple.png")
    
    print("=" * 50)
    print("流程图图片处理器")
    print("=" * 50)
    
    # 智能处理
    print("\n[1/2] 智能颜色转换...")
    process_flowchart(input_path, smart_output)
    
    # 简单反转
    print("\n[2/2] 简单颜色反转...")
    simple_invert(input_path, simple_output)
    
    print("\n" + "=" * 50)
    print("所有处理完成！")
    print("=" * 50)
