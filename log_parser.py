#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Android Log Parser
解析 Android am_kill 日志条目
"""

import re
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class LogEntry:
    """日志条目数据结构"""
    timestamp: str
    date: str
    time: str
    pid: int
    tid: int
    level: str
    tag: str
    raw_message: str
    parsed_data: Dict


class AndroidLogParser:
    """Android 日志解析器"""
    
    # 日志格式: MM-DD HH:MM:SS.microseconds  PID  TID LEVEL TAG : MESSAGE
    LOG_PATTERN = re.compile(
        r'(\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+(\S+)\s*:\s*(.+)'
    )
    
    @staticmethod
    def parse_am_kill_message(message: str) -> Dict:
        """
        解析 am_kill 消息格式: [flag,pid,package,importance,reason,duration]
        示例: [0,16920,com.ss.android.ugc.aweme,200,bg anr,563460]
        """
        # 移除方括号并分割
        if message.startswith('[') and message.endswith(']'):
            content = message[1:-1]
            parts = [p.strip() for p in content.split(',')]
            
            if len(parts) >= 6:
                return {
                    'flag': parts[0],
                    'process_id': int(parts[1]) if parts[1].isdigit() else parts[1],
                    'package_name': parts[2],
                    'importance': int(parts[3]) if parts[3].isdigit() else parts[3],
                    'reason': parts[4],
                    'duration_ms': int(parts[5]) if parts[5].isdigit() else parts[5],
                }
            elif len(parts) >= 4:
                # 兼容格式
                return {
                    'flag': parts[0],
                    'process_id': int(parts[1]) if parts[1].isdigit() else parts[1],
                    'package_name': parts[2],
                    'importance': int(parts[3]) if parts[3].isdigit() else parts[3],
                    'reason': parts[4] if len(parts) > 4 else '',
                    'duration_ms': int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else None,
                }
        
        return {'raw': message}
    
    @classmethod
    def parse(cls, log_line: str) -> Optional[LogEntry]:
        """
        解析单行日志
        
        Args:
            log_line: 日志行字符串
            
        Returns:
            LogEntry 对象或 None
        """
        match = cls.LOG_PATTERN.match(log_line.strip())
        if not match:
            return None
        
        date, time, pid, tid, level, tag, message = match.groups()
        timestamp = f"{date} {time}"
        
        # 解析特定标签的消息
        parsed_data = {}
        if tag == 'am_kill':
            parsed_data = cls.parse_am_kill_message(message)
        
        return LogEntry(
            timestamp=timestamp,
            date=date,
            time=time,
            pid=int(pid),
            tid=int(tid),
            level=level,
            tag=tag,
            raw_message=message,
            parsed_data=parsed_data
        )
    
    @staticmethod
    def format_output(entry: LogEntry) -> str:
        """格式化输出解析结果"""
        output = []
        output.append("=" * 60)
        output.append("日志解析结果")
        output.append("=" * 60)
        output.append(f"时间戳: {entry.timestamp}")
        output.append(f"日期: {entry.date}")
        output.append(f"时间: {entry.time}")
        output.append(f"进程ID (PID): {entry.pid}")
        output.append(f"线程ID (TID): {entry.tid}")
        output.append(f"日志级别: {entry.level} ({AndroidLogParser._get_level_name(entry.level)})")
        output.append(f"标签: {entry.tag}")
        output.append(f"原始消息: {entry.raw_message}")
        
        if entry.parsed_data:
            output.append("\n解析后的数据:")
            for key, value in entry.parsed_data.items():
                output.append(f"  {key}: {value}")
            
            # 特殊处理 am_kill
            if entry.tag == 'am_kill' and isinstance(entry.parsed_data, dict):
                output.append("\n详细说明:")
                if 'process_id' in entry.parsed_data:
                    output.append(f"  被杀死的进程ID: {entry.parsed_data['process_id']}")
                if 'package_name' in entry.parsed_data:
                    output.append(f"  应用包名: {entry.parsed_data['package_name']}")
                if 'importance' in entry.parsed_data:
                    importance = entry.parsed_data['importance']
                    output.append(f"  重要性: {importance} ({AndroidLogParser._get_importance_desc(importance)})")
                if 'reason' in entry.parsed_data:
                    reason = entry.parsed_data['reason']
                    output.append(f"  原因: {reason} ({AndroidLogParser._get_reason_desc(reason)})")
                if 'duration_ms' in entry.parsed_data and entry.parsed_data['duration_ms']:
                    duration = entry.parsed_data['duration_ms']
                    output.append(f"  持续时间: {duration} ms ({duration/1000:.2f} 秒)")
        
        output.append("=" * 60)
        return "\n".join(output)
    
    @staticmethod
    def _get_level_name(level: str) -> str:
        """获取日志级别名称"""
        levels = {
            'V': 'Verbose',
            'D': 'Debug',
            'I': 'Info',
            'W': 'Warning',
            'E': 'Error',
            'F': 'Fatal'
        }
        return levels.get(level, 'Unknown')
    
    @staticmethod
    def _get_importance_desc(importance) -> str:
        """获取重要性描述"""
        if isinstance(importance, int):
            if importance >= 400:
                return "前台应用"
            elif importance >= 300:
                return "可见但不可交互"
            elif importance >= 200:
                return "后台服务"
            elif importance >= 100:
                return "后台应用"
            else:
                return "空进程"
        return ""
    
    @staticmethod
    def _get_reason_desc(reason: str) -> str:
        """获取原因描述"""
        reasons = {
            'bg anr': '后台应用无响应 (Background ANR)',
            'anr': '应用无响应 (ANR)',
            'crash': '应用崩溃',
            'lowmemory': '内存不足',
            'kill': '系统杀死',
            'user': '用户请求',
        }
        return reasons.get(reason.lower(), '未知原因')


def main():
    """主函数"""
    # 示例日志
    log_line = "12-02 12:33:24.140988  2188 18274 I am_kill : [0,16920,com.ss.android.ugc.aweme,200,bg anr,563460]"
    
    parser = AndroidLogParser()
    entry = parser.parse(log_line)
    
    if entry:
        print(parser.format_output(entry))
    else:
        print("无法解析日志格式")


if __name__ == '__main__':
    main()
