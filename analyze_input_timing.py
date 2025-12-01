#!/usr/bin/env python3
"""
输入事件分发时间点分析工具
分析InputDispatcher日志中的关键时间点
"""

from datetime import datetime
from typing import List, Tuple
import re

# 日志条目
log_entries = [
    ("17:33:47.734775", "NFW_setFocusedWindow", "设置焦点窗口"),
    ("17:33:47.734803", "updateFocusedWindow", "更新焦点窗口"),
    ("17:33:47.734847", "currInputWindows", "更新输入窗口列表"),
    ("17:33:47.735026", "publishFocusEvent", "发布焦点事件到应用 ⭐"),
    ("17:33:49.491109", "dumpPreTrace", "ANR预追踪开始"),
    ("17:33:49.492257", "getThreadGroupLeader", "获取线程组信息"),
    ("17:33:49.496236", "preAnr notify", "ANR预通知"),
    ("17:33:51.491934", "onAnrLocked", "ANR确认"),
]

def parse_timestamp(ts: str) -> float:
    """解析时间戳为秒数（从当天00:00:00开始）"""
    time_part = ts.split()[0] if ' ' in ts else ts
    h, m, s = time_part.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)

def calculate_time_diff(ts1: str, ts2: str) -> float:
    """计算两个时间戳之间的差值（毫秒）"""
    t1 = parse_timestamp(ts1)
    t2 = parse_timestamp(ts2)
    return abs(t2 - t1) * 1000

def format_time_diff(ms: float) -> str:
    """格式化时间差"""
    if ms < 1:
        return f"{ms:.3f}ms"
    elif ms < 1000:
        return f"{ms:.2f}ms"
    else:
        return f"{ms/1000:.3f}秒"

def analyze_timing():
    """分析时间点"""
    print("=" * 80)
    print("输入事件分发时间点分析")
    print("=" * 80)
    print()
    
    # 基准时间点：事件发布到应用
    base_time = "17:33:47.735026"
    base_event = "publishFocusEvent (发布焦点事件到应用)"
    
    print(f"基准时间点: {base_time} - {base_event}")
    print()
    
    # 阶段1：焦点窗口设置
    print("【阶段1】焦点窗口设置阶段")
    print("-" * 80)
    stage1_start = parse_timestamp(log_entries[0][0])
    stage1_end = parse_timestamp(log_entries[3][0])
    stage1_duration = (stage1_end - stage1_start) * 1000
    
    for i in range(4):
        ts, event, desc = log_entries[i]
        if i == 0:
            print(f"{ts:20s} | {event:25s} | {desc}")
        else:
            prev_ts = log_entries[i-1][0]
            diff = calculate_time_diff(prev_ts, ts)
            print(f"{ts:20s} | {event:25s} | {desc:30s} | 延迟: {format_time_diff(diff)}")
    
    print(f"\n阶段总耗时: {format_time_diff(stage1_duration)}")
    print()
    
    # 阶段2：ANR检测
    print("【阶段2】ANR检测阶段")
    print("-" * 80)
    for i in range(4, len(log_entries)):
        ts, event, desc = log_entries[i]
        diff_from_base = calculate_time_diff(base_time, ts)
        if i == 4:
            print(f"{ts:20s} | {event:25s} | {desc:30s} | 距离事件发布: {format_time_diff(diff_from_base)}")
        else:
            prev_ts = log_entries[i-1][0]
            diff = calculate_time_diff(prev_ts, ts)
            print(f"{ts:20s} | {event:25s} | {desc:30s} | 距离事件发布: {format_time_diff(diff_from_base)} | 延迟: {format_time_diff(diff)}")
    
    print()
    
    # 关键指标
    print("【关键指标】")
    print("-" * 80)
    anr_pre_trace_time = log_entries[4][0]
    anr_confirmed_time = log_entries[7][0]
    
    event_to_anr_pre = calculate_time_diff(base_time, anr_pre_trace_time)
    event_to_anr_confirmed = calculate_time_diff(base_time, anr_confirmed_time)
    anr_pre_to_confirmed = calculate_time_diff(anr_pre_trace_time, anr_confirmed_time)
    
    print(f"1. 输入事件分发延迟（窗口设置→事件发布）: {format_time_diff(stage1_duration)}")
    print(f"2. 应用响应超时（事件发布→ANR预追踪）: {format_time_diff(event_to_anr_pre)}")
    print(f"3. ANR确认时间（事件发布→ANR确认）: {format_time_diff(event_to_anr_confirmed)}")
    print(f"4. ANR检测耗时（预追踪→确认）: {format_time_diff(anr_pre_to_confirmed)}")
    print()
    
    # 时间线可视化
    print("【时间线可视化】")
    print("-" * 80)
    all_times = [parse_timestamp(entry[0]) for entry in log_entries]
    min_time = min(all_times)
    max_time = max(all_times)
    time_range = max_time - min_time
    
    # 归一化到0-60字符宽度
    for i, (ts, event, desc) in enumerate(log_entries):
        normalized = (parse_timestamp(ts) - min_time) / time_range * 60
        bar = " " * int(normalized) + "|"
        marker = "⭐" if i == 3 else "•"
        print(f"{bar:65s} {marker} {ts} - {event}")
    
    print()
    
    # 结论
    print("【分析结论】")
    print("-" * 80)
    print("✓ InputDispatcher内部处理非常高效（0.251ms）")
    print(f"✗ 应用主线程在 {format_time_diff(event_to_anr_pre)} 内未响应输入事件")
    print(f"✗ ANR在 {format_time_diff(event_to_anr_confirmed)} 后确认")
    print()
    print("建议：")
    print("  1. 检查应用主线程是否有耗时操作阻塞")
    print("  2. 使用Traceview/Systrace分析应用执行情况")
    print("  3. 检查应用日志，确认是否有异常导致主线程阻塞")
    print("=" * 80)

if __name__ == "__main__":
    analyze_timing()
