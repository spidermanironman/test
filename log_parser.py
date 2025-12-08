#!/usr/bin/env python3
"""
Android log parser for am_kill logs
Parses logcat format: MM-DD HH:MM:SS.microseconds  PID TID LEVEL TAG : [parameters]
"""

import re
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class LogEntry:
    """Structured representation of a log entry"""
    date: str
    time: str
    microseconds: str
    pid: int
    tid: int
    level: str
    tag: str
    message: str
    parsed_data: Optional[Dict] = None


class AndroidLogParser:
    """Parser for Android logcat format"""
    
    # Pattern: MM-DD HH:MM:SS.microseconds  PID TID LEVEL TAG : message
    LOG_PATTERN = re.compile(
        r'(\d{2}-\d{2})\s+'  # Date: MM-DD
        r'(\d{2}:\d{2}:\d{2})\.(\d+)\s+'  # Time: HH:MM:SS.microseconds
        r'(\d+)\s+'  # PID
        r'(\d+)\s+'  # TID
        r'([VDIWEF])\s+'  # Log level
        r'(\w+)\s*:\s*'  # Tag
        r'(.*)'  # Message
    )
    
    @staticmethod
    def parse_log_line(log_line: str) -> Optional[LogEntry]:
        """Parse a single log line"""
        match = AndroidLogParser.LOG_PATTERN.match(log_line.strip())
        if not match:
            return None
        
        date, time, microseconds, pid, tid, level, tag, message = match.groups()
        
        entry = LogEntry(
            date=date,
            time=time,
            microseconds=microseconds,
            pid=int(pid),
            tid=int(tid),
            level=level,
            tag=tag,
            message=message
        )
        
        # Parse am_kill specific format: [0,16920,com.ss.android.ugc.aweme,200,bg anr,563460]
        if tag == 'am_kill' and message.startswith('[') and message.endswith(']'):
            entry.parsed_data = AndroidLogParser.parse_am_kill(message)
        
        return entry
    
    @staticmethod
    def parse_am_kill(message: str) -> Dict:
        """Parse am_kill message format: [param1,param2,param3,...]"""
        # Remove brackets and split by comma
        content = message.strip('[]')
        parts = []
        current = ''
        in_quotes = False
        
        # Handle commas inside quoted strings (like "bg anr")
        for char in content:
            if char == ',' and not in_quotes:
                parts.append(current.strip())
                current = ''
            elif char == ' ' and not in_quotes and current:
                # Space might be part of a value
                current += char
            else:
                current += char
        
        if current:
            parts.append(current.strip())
        
        # Parse the parts
        parsed = {}
        if len(parts) >= 6:
            parsed = {
                'unknown_field': parts[0],  # Usually 0
                'killed_pid': int(parts[1]) if parts[1].isdigit() else parts[1],
                'package_name': parts[2],
                'exit_code': int(parts[3]) if parts[3].isdigit() else parts[3],
                'reason': parts[4],  # e.g., "bg anr"
                'timestamp_or_id': int(parts[5]) if parts[5].isdigit() else parts[5]
            }
        elif len(parts) > 0:
            parsed = {'raw_parts': parts}
        
        return parsed
    
    @staticmethod
    def format_parsed_log(entry: LogEntry) -> str:
        """Format parsed log entry in a human-readable way"""
        output = []
        output.append("=" * 60)
        output.append("Log Entry")
        output.append("=" * 60)
        output.append(f"Date:        {entry.date}")
        output.append(f"Time:        {entry.time}.{entry.microseconds}")
        output.append(f"PID:         {entry.pid}")
        output.append(f"TID:         {entry.tid}")
        output.append(f"Level:       {entry.level}")
        output.append(f"Tag:         {entry.tag}")
        output.append(f"Message:     {entry.message}")
        
        if entry.parsed_data:
            output.append("\nParsed Data:")
            output.append("-" * 60)
            for key, value in entry.parsed_data.items():
                output.append(f"  {key:20s}: {value}")
        
        output.append("=" * 60)
        return "\n".join(output)


def main():
    """Main function to parse the provided log line"""
    log_line = "12-02 12:33:24.140988  2188 18274 I am_kill : [0,16920,com.ss.android.ugc.aweme,200,bg anr,563460]"
    
    print("Original log line:")
    print(log_line)
    print("\n")
    
    parser = AndroidLogParser()
    entry = parser.parse_log_line(log_line)
    
    if entry:
        print(parser.format_parsed_log(entry))
        
        # Additional analysis
        print("\nAnalysis:")
        print("-" * 60)
        if entry.parsed_data:
            print(f"Process killed: PID {entry.parsed_data.get('killed_pid')}")
            print(f"Package: {entry.parsed_data.get('package_name')}")
            print(f"Reason: {entry.parsed_data.get('reason')}")
            print(f"Exit code: {entry.parsed_data.get('exit_code')}")
            print("\nInterpretation:")
            print("  This log indicates that the Android ActivityManager (am_kill)")
            print("  killed a background process due to ANR (Application Not Responding).")
            print(f"  The process {entry.parsed_data.get('package_name')} (PID: {entry.parsed_data.get('killed_pid')})")
            print("  was terminated because it was not responding in the background.")
    else:
        print("Failed to parse log line")


if __name__ == "__main__":
    main()
