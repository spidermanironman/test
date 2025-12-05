#!/usr/bin/env python3
"""
检查处理广播的所有线程状态是否正常

这个脚本可以帮助检查Android系统中处理广播的线程状态。
可以通过分析日志、线程转储或运行时状态来验证所有广播处理线程是否正常。
"""

import re
import sys
from typing import List, Dict, Tuple
from enum import Enum


class ThreadState(Enum):
    """线程状态枚举"""
    RUNNABLE = "RUNNABLE"  # 可运行
    BLOCKED = "BLOCKED"    # 阻塞
    WAITING = "WAITING"    # 等待
    TIMED_WAITING = "TIMED_WAITING"  # 定时等待
    TERMINATED = "TERMINATED"  # 已终止
    UNKNOWN = "UNKNOWN"    # 未知


class BroadcastThreadChecker:
    """广播线程状态检查器"""
    
    def __init__(self):
        self.broadcast_threads = []
        self.thread_patterns = [
            r'BroadcastQueue',
            r'Binder.*broadcast',
            r'ActivityManager.*broadcast',
            r'BroadcastReceiver',
            r'Handler.*broadcast',
        ]
    
    def parse_thread_dump(self, dump_content: str) -> List[Dict]:
        """
        解析线程转储内容，提取广播相关线程
        
        Args:
            dump_content: 线程转储的文本内容
            
        Returns:
            包含线程信息的字典列表
        """
        threads = []
        current_thread = None
        
        lines = dump_content.split('\n')
        for i, line in enumerate(lines):
            # 检测线程开始（通常以 "---" 或线程名开始）
            if line.startswith('"') or 'tid=' in line or 'prio=' in line:
                if current_thread:
                    threads.append(current_thread)
                
                # 提取线程名
                thread_name_match = re.search(r'"([^"]+)"', line)
                if thread_name_match:
                    thread_name = thread_name_match.group(1)
                    # 检查是否是广播相关线程
                    if self._is_broadcast_thread(thread_name):
                        current_thread = {
                            'name': thread_name,
                            'state': ThreadState.UNKNOWN,
                            'tid': None,
                            'stack_trace': []
                        }
                        
                        # 提取线程ID
                        tid_match = re.search(r'tid=(\d+)', line)
                        if tid_match:
                            current_thread['tid'] = int(tid_match.group(1))
                else:
                    current_thread = None
            elif current_thread:
                # 提取线程状态
                state_match = re.search(r'java\.lang\.Thread\.State:\s*(\w+)', line)
                if state_match:
                    state_str = state_match.group(1)
                    try:
                        current_thread['state'] = ThreadState[state_str]
                    except KeyError:
                        current_thread['state'] = ThreadState.UNKNOWN
                
                # 收集堆栈跟踪
                if line.strip() and not line.startswith('---'):
                    current_thread['stack_trace'].append(line.strip())
        
        if current_thread:
            threads.append(current_thread)
        
        return threads
    
    def _is_broadcast_thread(self, thread_name: str) -> bool:
        """检查线程名是否与广播处理相关"""
        thread_name_lower = thread_name.lower()
        for pattern in self.thread_patterns:
            if re.search(pattern, thread_name_lower, re.IGNORECASE):
                return True
        return False
    
    def check_thread_states(self, threads: List[Dict]) -> Tuple[bool, List[str]]:
        """
        检查所有广播线程的状态是否正常
        
        Args:
            threads: 线程信息列表
            
        Returns:
            (是否全部正常, 问题描述列表)
        """
        issues = []
        all_normal = True
        
        if not threads:
            return False, ["未找到任何广播处理线程"]
        
        for thread in threads:
            thread_name = thread['name']
            state = thread['state']
            
            # 检查异常状态
            if state == ThreadState.BLOCKED:
                issues.append(f"线程 {thread_name} (tid={thread['tid']}) 处于 BLOCKED 状态，可能存在死锁")
                all_normal = False
            elif state == ThreadState.TERMINATED:
                issues.append(f"线程 {thread_name} (tid={thread['tid']}) 已终止")
                all_normal = False
            elif state == ThreadState.WAITING:
                # WAITING状态可能是正常的（等待消息），但需要检查堆栈
                if self._check_waiting_issue(thread):
                    issues.append(f"线程 {thread_name} (tid={thread['tid']}) 处于异常等待状态")
                    all_normal = False
        
        return all_normal, issues
    
    def _check_waiting_issue(self, thread: Dict) -> bool:
        """检查WAITING状态是否异常"""
        stack_trace = '\n'.join(thread['stack_trace'])
        
        # 检查是否有死锁迹象
        deadlock_indicators = [
            'deadlock',
            'LockSupport.park',
            'Object.wait',
            'Thread.sleep'
        ]
        
        # 如果等待时间过长或出现死锁迹象，认为异常
        for indicator in deadlock_indicators:
            if indicator in stack_trace:
                # 进一步检查是否是正常的等待
                if 'Handler' in stack_trace or 'MessageQueue' in stack_trace:
                    # Handler等待消息是正常的
                    return False
                return True
        
        return False
    
    def analyze_log(self, log_content: str) -> Dict:
        """
        分析日志内容，查找广播相关的线程状态信息
        
        Args:
            log_content: 日志内容
            
        Returns:
            分析结果字典
        """
        results = {
            'broadcast_events': [],
            'thread_errors': [],
            'anr_detected': False
        }
        
        lines = log_content.split('\n')
        
        for line in lines:
            # 检测广播事件
            if 'broadcast' in line.lower() and ('receive' in line.lower() or 'send' in line.lower()):
                results['broadcast_events'].append(line.strip())
            
            # 检测线程错误
            if 'thread' in line.lower() and ('error' in line.lower() or 'exception' in line.lower()):
                results['thread_errors'].append(line.strip())
            
            # 检测ANR
            if 'anr' in line.lower() or 'application not responding' in line.lower():
                results['anr_detected'] = True
                results['thread_errors'].append(line.strip())
        
        return results


def main():
    """主函数"""
    checker = BroadcastThreadChecker()
    
    print("=" * 60)
    print("广播线程状态检查工具")
    print("=" * 60)
    print()
    
    # 示例：从标准输入读取线程转储
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            print(f"错误: 文件 {input_file} 不存在")
            sys.exit(1)
    else:
        print("使用方法:")
        print("  python3 check_broadcast_thread_status.py <thread_dump_file>")
        print()
        print("或者从标准输入读取:")
        print("  adb shell dumpsys | python3 check_broadcast_thread_status.py -")
        print()
        print("示例检查逻辑:")
        print("1. 解析线程转储，查找所有广播相关线程")
        print("2. 检查每个线程的状态:")
        print("   - RUNNABLE: 正常")
        print("   - WAITING: 通常正常（等待消息）")
        print("   - BLOCKED: 可能存在问题（死锁风险）")
        print("   - TERMINATED: 异常（线程已终止）")
        print("3. 检查堆栈跟踪，识别潜在问题")
        print()
        
        # 提供示例检查结果
        print("示例输出:")
        print("-" * 60)
        print("检查结果: 所有广播处理线程状态正常")
        print()
        print("发现的广播线程:")
        print("  1. BroadcastQueue (tid=1234) - RUNNABLE")
        print("  2. Binder:1234_1 (tid=5678) - WAITING (正常等待消息)")
        print("  3. ActivityManager (tid=9012) - RUNNABLE")
        print()
        print("如何判断线程状态正常:")
        print("  ✓ 线程状态为 RUNNABLE 或 WAITING（等待Handler消息）")
        print("  ✓ 没有 BLOCKED 状态（可能表示死锁）")
        print("  ✓ 没有 TERMINATED 状态（线程不应终止）")
        print("  ✓ 堆栈跟踪中没有异常等待或死锁迹象")
        print("  ✓ 日志中没有ANR（Application Not Responding）报告")
        print("-" * 60)
        return
    
    # 解析线程转储
    threads = checker.parse_thread_dump(content)
    
    if not threads:
        print("未找到广播相关的线程")
        sys.exit(1)
    
    print(f"找到 {len(threads)} 个广播相关线程:")
    print()
    
    for i, thread in enumerate(threads, 1):
        print(f"{i}. {thread['name']} (tid={thread['tid']})")
        print(f"   状态: {thread['state'].value}")
        if thread['stack_trace']:
            print(f"   堆栈跟踪 (前3行):")
            for line in thread['stack_trace'][:3]:
                print(f"     {line}")
        print()
    
    # 检查线程状态
    all_normal, issues = checker.check_thread_states(threads)
    
    print("=" * 60)
    if all_normal:
        print("✓ 检查结果: 所有广播处理线程状态均正常")
    else:
        print("✗ 检查结果: 发现异常线程状态")
        print()
        print("问题列表:")
        for issue in issues:
            print(f"  - {issue}")
    print("=" * 60)


if __name__ == '__main__':
    main()
