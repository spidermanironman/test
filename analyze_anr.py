#!/usr/bin/env python3
"""
分析Android ANR日志，找出主线程等待的日志锁
"""

import re
from collections import defaultdict

def parse_anr_log(log_content):
    """解析ANR日志"""
    lines = log_content.split('\n')
    
    # 存储每个线程的堆栈信息
    threads = {}
    current_thread = None
    current_stack = []
    
    # 存储等待日志锁的线程
    waiting_for_log_lock = []
    
    # 存储持有日志锁的线程（在日志相关函数中）
    in_logging_code = []
    
    for i, line in enumerate(lines):
        # 匹配线程标题行，例如: "m.tencent.KiHan" sysTid=19671
        thread_match = re.match(r'^"([^"]+)"\s+sysTid=(\d+)', line)
        if thread_match:
            if current_thread:
                threads[current_thread['tid']] = {
                    'name': current_thread['name'],
                    'stack': current_stack
                }
            current_thread = {
                'name': thread_match.group(1),
                'tid': int(thread_match.group(2))
            }
            current_stack = []
            continue
        
        # 匹配堆栈帧，例如: #00 pc 00000000000affe0  /apex/com.android.runtime/lib64/bionic/libc.so (syscall+32)
        stack_match = re.match(r'^\s+#\d+\s+pc\s+[0-9a-f]+\s+(.+?)\s+\((.+?)\)', line)
        if stack_match and current_thread:
            lib_path = stack_match.group(1)
            function = stack_match.group(2)
            current_stack.append({
                'lib': lib_path,
                'function': function
            })
            
            # 检查是否在日志相关代码中
            if any(keyword in function.lower() or keyword in lib_path.lower() 
                   for keyword in ['log', 'logger', 'logd', 'trace']):
                in_logging_code.append({
                    'tid': current_thread['tid'],
                    'name': current_thread['name'],
                    'function': function,
                    'lib': lib_path
                })
    
    # 保存最后一个线程
    if current_thread:
        threads[current_thread['tid']] = {
            'name': current_thread['name'],
            'stack': current_stack
        }
    
    return threads, waiting_for_log_lock, in_logging_code

def analyze_main_thread_waiting(anr_log):
    """分析主线程等待日志锁的情况"""
    
    # 查找主线程
    main_thread_match = re.search(r'"m\.tencent\.KiHan"\s+sysTid=(\d+)', anr_log)
    if not main_thread_match:
        return None
    
    main_tid = int(main_thread_match.group(1))
    
    # 提取主线程堆栈
    main_thread_section = re.search(
        rf'"m\.tencent\.KiHan"\s+sysTid={main_tid}(.*?)(?=\n"[^"]+"\s+sysTid=|\n-----|\Z)',
        anr_log,
        re.DOTALL
    )
    
    if not main_thread_section:
        return None
    
    main_stack = main_thread_section.group(1)
    
    # 检查主线程是否在等待日志锁
    log_lock_patterns = [
        r'LogdLoggerLocked',
        r'mutex::lock',
        r'NonPI::MutexLockWithTimeout',
        r'trace_begin_internal',
        r'ScopedTrace'
    ]
    
    is_waiting_log_lock = any(re.search(pattern, main_stack) for pattern in log_lock_patterns)
    
    if not is_waiting_log_lock:
        return None
    
    # 提取所有线程信息
    threads = {}
    thread_pattern = r'"([^"]+)"\s+sysTid=(\d+)(.*?)(?=\n"[^"]+"\s+sysTid=|\n-----|\Z)'
    
    for match in re.finditer(thread_pattern, anr_log, re.DOTALL):
        thread_name = match.group(1)
        thread_tid = int(match.group(2))
        thread_stack = match.group(3)
        
        threads[thread_tid] = {
            'name': thread_name,
            'stack': thread_stack
        }
    
    # 查找可能在日志相关代码中执行的线程
    potential_lock_holders = []
    
    for tid, thread_info in threads.items():
        if tid == main_tid:
            continue
        
        stack = thread_info['stack']
        
        # 检查是否在日志相关函数中
        log_functions = [
            'LogdLoggerLocked',
            'trace_begin_internal',
            'trace_end_internal',
            'ScopedTrace',
            'LogdLogger',
            '__android_log',
            'android_util_Log'
        ]
        
        for func in log_functions:
            if func in stack:
                potential_lock_holders.append({
                    'tid': tid,
                    'name': thread_info['name'],
                    'stack': stack
                })
                break
    
    return {
        'main_tid': main_tid,
        'main_stack': main_stack,
        'potential_lock_holders': potential_lock_holders,
        'all_threads': threads
    }

def main():
    # 读取ANR日志（从标准输入或文件）
    import sys
    
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8', errors='ignore') as f:
            anr_log = f.read()
    else:
        # 从用户输入读取
        anr_log = sys.stdin.read()
    
    result = analyze_main_thread_waiting(anr_log)
    
    if not result:
        print("未找到主线程等待日志锁的情况")
        return
    
    print("=" * 80)
    print("主线程等待日志锁分析")
    print("=" * 80)
    print(f"\n主线程 TID: {result['main_tid']}")
    print("\n主线程堆栈（关键部分）:")
    print("-" * 80)
    
    # 显示主线程堆栈的关键部分
    main_stack_lines = result['main_stack'].split('\n')
    for line in main_stack_lines[:15]:  # 显示前15行
        if line.strip():
            print(line)
    
    print("\n" + "=" * 80)
    print("可能持有日志锁的线程:")
    print("=" * 80)
    
    if result['potential_lock_holders']:
        for i, holder in enumerate(result['potential_lock_holders'], 1):
            print(f"\n[{i}] 线程 TID: {holder['tid']}, 名称: {holder['name']}")
            print("-" * 80)
            # 显示堆栈的关键部分
            stack_lines = holder['stack'].split('\n')
            for line in stack_lines[:20]:  # 显示前20行
                if line.strip() and line.strip().startswith('#'):
                    print(line)
    else:
        print("\n未找到明显持有日志锁的线程")
        print("\n建议检查所有线程的堆栈，查找在日志相关函数中执行的线程")
    
    print("\n" + "=" * 80)
    print("分析建议:")
    print("=" * 80)
    print("""
1. 主线程在 LogdLoggerLocked::operator() 中调用 mutex::lock() 时被阻塞
2. 这表明另一个线程正在持有日志系统的互斥锁
3. 需要检查所有线程的堆栈，找出正在执行日志相关代码的线程
4. 常见原因：
   - 某个线程在执行日志输出时被阻塞（如I/O操作）
   - 日志系统内部死锁
   - 大量并发日志导致锁竞争
    """)

if __name__ == '__main__':
    main()
