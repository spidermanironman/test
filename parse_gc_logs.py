#!/usr/bin/env python3
"""
解析 Android GC 日志，提取堆内存信息
"""

import re
import sys
from typing import List, Dict, Optional

def parse_gc_line(line: str) -> Optional[Dict]:
    """
    解析单行 GC 日志
    
    格式示例:
    Alloc concurrent copying GC freed 362KB AllocSpace bytes, 5(148KB) LOS objects, 
    14% free,549MB(M:180MB,L:368MB)/645MB, paused 149us,277us total 2.002s
    """
    # 匹配内存信息部分: 549MB(M:180MB,L:368MB)/645MB
    pattern = r'(\d+)% free,(\d+)MB\(M:(\d+)MB,L:(\d+)MB\)/(\d+)MB'
    match = re.search(pattern, line)
    
    if not match:
        return None
    
    free_percent = int(match.group(1))
    used_mb = int(match.group(2))
    m_mb = int(match.group(3))
    l_mb = int(match.group(4))
    total_mb = int(match.group(5))
    
    # 提取 freed 信息
    freed_match = re.search(r'freed ([\d.]+)(KB|MB)', line)
    freed_size = 0
    if freed_match:
        freed_size = float(freed_match.group(1))
        unit = freed_match.group(2)
        if unit == 'MB':
            freed_size = freed_size * 1024  # 转换为 KB
    
    # 提取 paused 和 total 时间
    paused_match = re.search(r'paused ([\d.]+)(us|ms)', line)
    paused_time = 0
    if paused_match:
        paused_time = float(paused_match.group(1))
        if paused_match.group(2) == 'ms':
            paused_time = paused_time * 1000  # 转换为 us
    
    total_match = re.search(r'total ([\d.]+)(us|ms|s)', line)
    total_time = 0
    if total_match:
        total_time = float(total_match.group(1))
        unit = total_match.group(2)
        if unit == 's':
            total_time = total_time * 1000  # 转换为 ms
        elif unit == 'us':
            total_time = total_time / 1000  # 转换为 ms
    
    return {
        'free_percent': free_percent,
        'used_mb': used_mb,
        'm_mb': m_mb,
        'l_mb': l_mb,
        'total_mb': total_mb,
        'freed_kb': freed_size,
        'paused_us': paused_time,
        'total_ms': total_time
    }


def analyze_logs(log_lines: List[str]) -> Dict:
    """分析所有日志行"""
    parsed_logs = []
    for line in log_lines:
        parsed = parse_gc_line(line)
        if parsed:
            parsed_logs.append(parsed)
    
    if not parsed_logs:
        return {'error': '未找到有效的 GC 日志'}
    
    # 统计信息
    total_heap_sizes = [log['total_mb'] for log in parsed_logs]
    used_heap_sizes = [log['used_mb'] for log in parsed_logs]
    
    return {
        'total_count': len(parsed_logs),
        'heap_size_mb': {
            'min': min(total_heap_sizes),
            'max': max(total_heap_sizes),
            'avg': sum(total_heap_sizes) / len(total_heap_sizes),
            'current': total_heap_sizes[-1]  # 最新的堆大小
        },
        'used_heap_mb': {
            'min': min(used_heap_sizes),
            'max': max(used_heap_sizes),
            'avg': sum(used_heap_sizes) / len(used_heap_sizes),
            'current': used_heap_sizes[-1]
        },
        'free_percent': {
            'min': min(log['free_percent'] for log in parsed_logs),
            'max': max(log['free_percent'] for log in parsed_logs),
            'avg': sum(log['free_percent'] for log in parsed_logs) / len(parsed_logs)
        },
        'all_logs': parsed_logs
    }


def main():
    """主函数"""
    if len(sys.argv) > 1:
        # 从文件读取
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            lines = f.readlines()
    else:
        # 从标准输入读取
        lines = sys.stdin.readlines()
    
    result = analyze_logs(lines)
    
    if 'error' in result:
        print(result['error'])
        return
    
    print("=" * 60)
    print("GC 日志分析结果")
    print("=" * 60)
    print(f"\n总日志条数: {result['total_count']}")
    print(f"\n堆内存大小 (MB):")
    print(f"  当前: {result['heap_size_mb']['current']} MB")
    print(f"  最小: {result['heap_size_mb']['min']} MB")
    print(f"  最大: {result['heap_size_mb']['max']} MB")
    print(f"  平均: {result['heap_size_mb']['avg']:.2f} MB")
    
    print(f"\n已使用堆内存 (MB):")
    print(f"  当前: {result['used_heap_mb']['current']} MB")
    print(f"  最小: {result['used_heap_mb']['min']} MB")
    print(f"  最大: {result['used_heap_mb']['max']} MB")
    print(f"  平均: {result['used_heap_mb']['avg']:.2f} MB")
    
    print(f"\n空闲百分比:")
    print(f"  最小: {result['free_percent']['min']}%")
    print(f"  最大: {result['free_percent']['max']}%")
    print(f"  平均: {result['free_percent']['avg']:.2f}%")
    
    print("\n" + "=" * 60)
    print("详细日志信息:")
    print("=" * 60)
    for i, log in enumerate(result['all_logs'], 1):
        print(f"\n日志 {i}:")
        print(f"  堆大小: {log['total_mb']} MB")
        print(f"  已使用: {log['used_mb']} MB")
        print(f"  空闲: {log['free_percent']}%")
        print(f"  释放: {log['freed_kb']:.2f} KB")
        print(f"  暂停时间: {log['paused_us']:.2f} us")
        print(f"  总时间: {log['total_ms']:.2f} ms")


if __name__ == '__main__':
    main()
