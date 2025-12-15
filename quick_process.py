#!/usr/bin/env python3
"""
快速处理流程图图片
用法: python quick_process.py <输入图片路径>
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import sys
import os

def process(input_path):
    """处理流程图：黑底变白底，浅色文字变深色"""
    
    # 读取图片
    img = cv2.imread(input_path)
    if img is None:
        print(f"无法读取图片: {input_path}")
        return
    
    print(f"原始尺寸: {img.shape[1]}x{img.shape[0]}")
    
    # 转RGB
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(img_hsv)
    
    # 创建白色背景的结果
    result = np.full_like(img_rgb, 255, dtype=np.uint8)
    
    # 处理各种像素
    # 1. 深色背景 -> 白色（已经是白色背景了）
    # 2. 浅色/灰色元素 -> 深色
    bg_mask = v < 40
    light_mask = (v > 150) & (s < 50)
    mid_mask = (v >= 40) & (v <= 150) & (s < 50)
    colored_mask = (s >= 50) & ~bg_mask
    
    # 浅色变深色
    result[light_mask] = [35, 35, 35]
    
    # 中间灰度反转
    mid_v = v[mid_mask]
    inverted_v = 255 - mid_v
    for i in range(3):
        result[:,:,i][mid_mask] = inverted_v
    
    # 彩色元素保留但加深
    if np.any(colored_mask):
        for i in range(3):
            result[:,:,i][colored_mask] = (img_rgb[:,:,i][colored_mask] * 0.8).astype(np.uint8)
    
    # 转PIL并增强
    pil_img = Image.fromarray(result)
    
    # 锐化
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.4)
    # 对比度
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.1)
    # USM锐化
    pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=100, threshold=2))
    
    # 2倍放大
    w, h = pil_img.size
    pil_img = pil_img.resize((w*2, h*2), Image.LANCZOS)
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.2)
    
    # 保存
    base = os.path.splitext(input_path)[0]
    output_path = f"{base}_processed.png"
    pil_img.save(output_path, quality=95)
    
    print(f"✓ 处理完成: {output_path}")
    print(f"  新尺寸: {w*2}x{h*2}")
    
    return output_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python quick_process.py <图片路径>")
    else:
        process(sys.argv[1])
