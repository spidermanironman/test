#!/usr/bin/env python3
"""
分析 Android InputDispatcher 日志，提取输入事件分发到应用的时间点
"""

import re
from datetime import datetime
from typing import List, Dict, Tuple

def parse_timestamp(log_line: str) -> Tuple[float, str]:
    """
    解析日志时间戳
    格式: 11-24 17:33:47.734775
    返回: (秒数, 原始时间字符串)
    """
    match = re.search(r'(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6})', log_line)
    if match:
        time_str = match.group(1)
        # 解析为秒数（相对于某个基准点）
        parts = time_str.split()
        date_part = parts[0]  # 11-24
        time_part = parts[1]  # 17:33:47.734775
        
        # 提取时分秒和微秒
        time_components = time_part.split('.')
        hms = time_components[0].split(':')
        microseconds = int(time_components[1]) if len(time_components) > 1 else 0
        
        hours = int(hms[0])
        minutes = int(hms[1])
        seconds = int(hms[2])
        
        # 转换为总秒数（从当天 00:00:00 开始）
        total_seconds = hours * 3600 + minutes * 60 + seconds + microseconds / 1_000_000
        
        return total_seconds, time_str
    return None, None

def analyze_input_timing(logs: List[str]) -> Dict:
    """分析输入事件分发时间线"""
    
    events = []
    
    for i, log in enumerate(logs, start=1):
        timestamp, time_str = parse_timestamp(log)
        if timestamp is None:
            continue
            
        event_type = None
        details = {}
        
        # 识别关键事件类型
        if 'NFW_setFocusedWindow' in log:
            event_type = 'setFocusedWindow'
            # 提取窗口信息
            match = re.search(r'(\w+) ([\w.]+/[\w.]+)', log)
            if match:
                details['window_token'] = match.group(1)
                details['activity'] = match.group(2)
                
        elif 'updateFocusedWindow' in log:
            event_type = 'updateFocusedWindow'
            match = re.search(r'reason: (\w+)', log)
            if match:
                details['reason'] = match.group(1)
                
        elif 'currInputWindows' in log:
            event_type = 'currentInputWindows'
            # 提取窗口列表
            match = re.search(r'currInputWindows displayId=(\d+)', log)
            if match:
                details['display_id'] = match.group(1)
                
        elif 'publishFocusEvent' in log:
            event_type = 'publishFocusEvent'
            match = re.search(r"channel '([^']+)'", log)
            if match:
                details['channel'] = match.group(1)
            match = re.search(r'hasFocus=(\w+)', log)
            if match:
                details['has_focus'] = match.group(1) == 'true'
                
        elif 'dumpPreTrace' in log:
            event_type = 'anrPreTrace'
            match = re.search(r'pid = (\d+)', log)
            if match:
                details['pid'] = match.group(1)
                
        elif 'onAnrLocked' in log or 'is not responding' in log:
            event_type = 'anrConfirmed'
            match = re.search(r'(\w+) ([\w.]+/[\w.]+)', log)
            if match:
                details['window_token'] = match.group(1)
                details['activity'] = match.group(2)
            match = re.search(r'seq=(\d+)', log)
            if match:
                details['sequence'] = match.group(1)
        
        if event_type:
            events.append({
                'line': i,
                'timestamp': timestamp,
                'time_str': time_str,
                'type': event_type,
                'details': details,
                'raw_log': log.strip()
            })
    
    # 计算时间间隔
    if len(events) > 1:
        base_time = events[0]['timestamp']
        for event in events:
            event['time_offset'] = event['timestamp'] - base_time
    
    return {
        'events': events,
        'summary': generate_summary(events)
    }

def generate_summary(events: List[Dict]) -> Dict:
    """生成分析摘要"""
    if not events:
        return {}
    
    summary = {
        'total_events': len(events),
        'time_span': None,
        'key_intervals': {}
    }
    
    if len(events) > 1:
        first_time = events[0]['timestamp']
        last_time = events[-1]['timestamp']
        summary['time_span'] = last_time - first_time
        
        # 查找关键时间间隔
        focus_event = next((e for e in events if e['type'] == 'publishFocusEvent'), None)
        anr_pre = next((e for e in events if e['type'] == 'anrPreTrace'), None)
        anr_confirmed = next((e for e in events if e['type'] == 'anrConfirmed'), None)
        
        if focus_event and anr_pre:
            summary['key_intervals']['focus_to_anr_pre'] = anr_pre['timestamp'] - focus_event['timestamp']
        
        if anr_pre and anr_confirmed:
            summary['key_intervals']['anr_pre_to_confirmed'] = anr_confirmed['timestamp'] - anr_pre['timestamp']
        
        if focus_event and anr_confirmed:
            summary['key_intervals']['focus_to_anr'] = anr_confirmed['timestamp'] - focus_event['timestamp']
    
    return summary

def print_analysis(result: Dict):
    """打印分析结果"""
    print("=" * 80)
    print("Android InputDispatcher 事件时间线分析")
    print("=" * 80)
    print()
    
    events = result['events']
    summary = result['summary']
    
    print("事件序列:")
    print("-" * 80)
    for event in events:
        offset_str = f"+{event.get('time_offset', 0):.6f}s" if 'time_offset' in event else ""
        print(f"行 {event['line']:6d} | {event['time_str']} {offset_str:>12}")
        print(f"        类型: {event['type']}")
        if event['details']:
            for key, value in event['details'].items():
                print(f"        {key}: {value}")
        print()
    
    print("=" * 80)
    print("关键时间间隔分析:")
    print("-" * 80)
    
    if summary.get('time_span'):
        print(f"总时间跨度: {summary['time_span']:.6f} 秒 ({summary['time_span']*1000:.2f} 毫秒)")
        print()
    
    intervals = summary.get('key_intervals', {})
    if 'focus_to_anr_pre' in intervals:
        interval = intervals['focus_to_anr_pre']
        print(f"焦点事件发布 → ANR 预追踪: {interval:.6f} 秒 ({interval*1000:.2f} 毫秒)")
        print("  (这是从应用获得焦点到系统开始检测 ANR 的时间)")
        print()
    
    if 'anr_pre_to_confirmed' in intervals:
        interval = intervals['anr_pre_to_confirmed']
        print(f"ANR 预追踪 → ANR 确认: {interval:.6f} 秒 ({interval*1000:.2f} 毫秒)")
        print("  (这是 ANR 检测窗口期，通常为 2 秒)")
        print()
    
    if 'focus_to_anr' in intervals:
        interval = intervals['focus_to_anr']
        print(f"焦点事件发布 → ANR 确认: {interval:.6f} 秒 ({interval*1000:.2f} 毫秒)")
        print("  (从应用获得焦点到最终确认 ANR 的总时间)")
        print()
    
    print("=" * 80)
    print("分析结论:")
    print("-" * 80)
    
    # 查找焦点事件和 ANR 事件
    focus_event = next((e for e in events if e['type'] == 'publishFocusEvent'), None)
    anr_event = next((e for e in events if e['type'] == 'anrConfirmed'), None)
    
    if focus_event:
        print(f"✓ 应用获得焦点时间: {focus_event['time_str']}")
        if 'channel' in focus_event['details']:
            print(f"  窗口: {focus_event['details']['channel']}")
    
    if anr_event:
        print(f"✗ ANR 确认时间: {anr_event['time_str']}")
        if 'activity' in anr_event['details']:
            print(f"  应用: {anr_event['details']['activity']}")
        if 'sequence' in anr_event['details']:
            print(f"  序列号: {anr_event['details']['sequence']}")
    
    if focus_event and anr_event:
        interval = anr_event['timestamp'] - focus_event['timestamp']
        print(f"\n从获得焦点到 ANR 的时间: {interval:.6f} 秒 ({interval*1000:.2f} 毫秒)")
        print("\n可能的原因:")
        print("  1. 应用主线程被阻塞，无法处理输入事件")
        print("  2. 应用在获得焦点后执行了耗时操作")
        print("  3. 输入事件队列积压，应用无法及时响应")

if __name__ == '__main__':
    # 用户提供的日志
    logs = [
        "行 272238: 11-24 17:33:47.734775  3392  6976 I InputDispatcher: NFW_setFocusedWindow, a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity on display 0, same as the previous:0",
        "行 272239: 11-24 17:33:47.734803  3392  6976 I InputDispatcher: updateFocusedWindow, a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity on display 0, reason: setFocusedWindow, result:   FocusedWindows:",
        "行 272242: 11-24 17:33:47.734847  3392  6976 V InputDispatcher: currInputWindows displayId=0 {e845aa NavigationBar_displayId_0,0,id=85,ownerPid=6633,iC=0x104,a=1.00,tR=<empty>} {70fa60d StatusBar,0,id=96,ownerPid=6633,iC=0x104,a=1.00,tR=[1131,0][1272,2772]} {6a8710 New Notification Barrage Window2,0,id=6387,ownerPid=9677,i ...",
        "行 272243: 11-24 17:33:47.735026  3392  5341 V InputDispatcher: channel 'a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity' ~  publishFocusEvent(hasFocus=true)",
        "行 272525: 11-24 17:33:49.491109  3392  5341 I InputDispatcherExtImpl: dumpPreTrace: pid = 19671",
        "行 272526: 11-24 17:33:49.492257  3392  5341 I InputDispatcherExtImpl: getThreadGroupLeader, pid 19671, return tgid 19671",
        "行 272527: 11-24 17:33:49.496236  3392  5341 D OplusActivityManagerServiceEnhance: InputDispatcher preAnr notify hans to check uid 10370 frozen state",
        "行 272784: 11-24 17:33:51.491934  3392  5341 I InputDispatcher: AnrLogEnhancement:onAnrLocked a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity is not responding seq=24937847"
    ]
    
    result = analyze_input_timing(logs)
    print_analysis(result)
