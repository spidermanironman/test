#!/usr/bin/env python3
"""
微信 Native Crash 注入测试工具

用途：安全测试、崩溃处理机制测试、稳定性测试

依赖：
    pip install frida frida-tools

使用方法：
    python run_crash_test.py [选项]

示例：
    python run_crash_test.py                    # 附加到运行中的微信
    python run_crash_test.py --spawn            # 启动微信并注入
    python run_crash_test.py --crash abort      # 自动触发 abort crash
    python run_crash_test.py --delay 10         # 10秒后触发 crash
"""

import argparse
import sys
import time
import os

try:
    import frida
except ImportError:
    print("错误: 请先安装 frida")
    print("运行: pip install frida frida-tools")
    sys.exit(1)


# 微信包名
WECHAT_PACKAGE = "com.tencent.mm"

# 脚本路径
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wechat_native_crash.js")


def on_message(message, data):
    """处理来自 Frida 脚本的消息"""
    if message['type'] == 'send':
        print(f"[脚本] {message['payload']}")
    elif message['type'] == 'error':
        print(f"[错误] {message['stack']}")
    else:
        print(f"[消息] {message}")


def load_script():
    """加载 Frida 脚本"""
    with open(SCRIPT_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def list_devices():
    """列出可用设备"""
    print("\n可用设备:")
    print("-" * 50)
    for device in frida.enumerate_devices():
        print(f"  {device.id}: {device.name} ({device.type})")
    print("-" * 50)


def get_device(device_id=None):
    """获取目标设备"""
    if device_id:
        return frida.get_device(device_id)
    
    # 优先使用 USB 设备
    try:
        return frida.get_usb_device(timeout=5)
    except frida.TimedOutError:
        print("警告: 未找到 USB 设备，使用本地设备")
        return frida.get_local_device()


def find_wechat_process(device):
    """查找微信进程"""
    for process in device.enumerate_processes():
        if WECHAT_PACKAGE in process.name or 'wechat' in process.name.lower():
            return process
    return None


def inject_and_crash(args):
    """注入脚本并触发 crash"""
    
    print(f"\n{'='*50}")
    print("  微信 Native Crash 注入工具")
    print(f"{'='*50}\n")
    
    # 获取设备
    device = get_device(args.device)
    print(f"[*] 使用设备: {device.name}")
    
    session = None
    script = None
    
    try:
        if args.spawn:
            # 启动微信并注入
            print(f"[*] 启动微信: {WECHAT_PACKAGE}")
            pid = device.spawn([WECHAT_PACKAGE])
            session = device.attach(pid)
            print(f"[+] 已附加到进程 PID: {pid}")
            
            # 加载脚本
            script_code = load_script()
            
            # 修改配置
            if args.crash:
                script_code = script_code.replace(
                    "autoTrigger: false",
                    "autoTrigger: true"
                )
                script_code = script_code.replace(
                    f"crashType: 'null_pointer'",
                    f"crashType: '{args.crash}'"
                )
            
            if args.delay:
                script_code = script_code.replace(
                    "triggerDelay: 5000",
                    f"triggerDelay: {args.delay * 1000}"
                )
            
            script = session.create_script(script_code)
            script.on('message', on_message)
            script.load()
            
            # 恢复进程
            device.resume(pid)
            print("[+] 微信已启动")
            
        else:
            # 附加到已运行的微信
            process = find_wechat_process(device)
            if not process:
                print(f"[-] 未找到微信进程，请先启动微信或使用 --spawn 选项")
                return 1
            
            print(f"[*] 找到微信进程: {process.name} (PID: {process.pid})")
            session = device.attach(process.pid)
            print(f"[+] 已附加到进程")
            
            # 加载脚本
            script_code = load_script()
            
            # 修改配置
            if args.crash:
                script_code = script_code.replace(
                    "autoTrigger: false",
                    "autoTrigger: true"
                )
                script_code = script_code.replace(
                    "crashType: 'null_pointer'",
                    f"crashType: '{args.crash}'"
                )
            
            if args.delay:
                script_code = script_code.replace(
                    "triggerDelay: 5000",
                    f"triggerDelay: {args.delay * 1000}"
                )
            
            script = session.create_script(script_code)
            script.on('message', on_message)
            script.load()
        
        print("\n[*] 脚本已注入，进入交互模式")
        print("[*] 在 Frida 控制台中输入 help() 查看可用命令")
        print("[*] 按 Ctrl+C 退出\n")
        
        # 保持运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] 用户中断，退出...")
            
    except frida.ProcessNotFoundError:
        print(f"[-] 未找到进程: {WECHAT_PACKAGE}")
        return 1
    except frida.ServerNotRunningError:
        print("[-] Frida server 未运行")
        print("    请在设备上启动 frida-server:")
        print("    adb shell '/data/local/tmp/frida-server &'")
        return 1
    except Exception as e:
        print(f"[-] 错误: {e}")
        return 1
    finally:
        if script:
            script.unload()
        if session:
            session.detach()
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='微信 Native Crash 注入测试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s                          附加到运行中的微信
  %(prog)s --spawn                  启动微信并注入
  %(prog)s --crash abort            自动触发 abort crash
  %(prog)s --crash null_pointer     自动触发空指针 crash
  %(prog)s --delay 10               10秒后触发 crash
  %(prog)s --list-devices           列出可用设备

Crash 类型:
  null_pointer    空指针解引用 (SIGSEGV)
  abort           调用 abort() (SIGABRT)
  segfault        段错误 (SIGSEGV)
  stack_overflow  栈溢出
  divide_zero     除零错误 (SIGFPE)
  sigkill         SIGKILL 信号
  sigabrt         SIGABRT 信号
  sigsegv         SIGSEGV 信号
        '''
    )
    
    parser.add_argument('--spawn', '-s', action='store_true',
                        help='启动微信并注入（而不是附加到已运行的进程）')
    
    parser.add_argument('--crash', '-c', type=str,
                        choices=['null_pointer', 'abort', 'segfault', 
                                'stack_overflow', 'divide_zero',
                                'sigkill', 'sigabrt', 'sigsegv'],
                        help='自动触发指定类型的 crash')
    
    parser.add_argument('--delay', '-d', type=int, default=5,
                        help='触发 crash 前的延迟秒数 (默认: 5)')
    
    parser.add_argument('--device', type=str,
                        help='指定设备 ID')
    
    parser.add_argument('--list-devices', '-l', action='store_true',
                        help='列出可用设备')
    
    parser.add_argument('--package', '-p', type=str, default=WECHAT_PACKAGE,
                        help=f'目标包名 (默认: {WECHAT_PACKAGE})')
    
    args = parser.parse_args()
    
    if args.list_devices:
        list_devices()
        return 0
    
    global WECHAT_PACKAGE
    WECHAT_PACKAGE = args.package
    
    return inject_and_crash(args)


if __name__ == '__main__':
    sys.exit(main())
