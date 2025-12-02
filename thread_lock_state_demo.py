"""
演示主线程等待锁时的状态
"""
import threading
import time

# 创建一个锁
lock = threading.Lock()

def worker_thread():
    """工作线程：获取锁并持有一段时间"""
    print(f"[工作线程] 尝试获取锁...")
    lock.acquire()
    print(f"[工作线程] 已获取锁，持有5秒...")
    time.sleep(5)  # 持有锁5秒
    lock.release()
    print(f"[工作线程] 释放锁")

def main():
    """主线程：尝试获取已被占用的锁"""
    print("=" * 50)
    print("主线程等待锁的状态演示")
    print("=" * 50)
    
    # 先让工作线程获取锁
    worker = threading.Thread(target=worker_thread)
    worker.start()
    
    # 等待一下，确保工作线程先获取锁
    time.sleep(0.1)
    
    print(f"\n[主线程] 尝试获取锁（此时锁已被工作线程持有）...")
    print(f"[主线程] 当前状态: {threading.current_thread().is_alive()}")
    
    # 主线程尝试获取锁，会被阻塞
    print(f"[主线程] 调用 lock.acquire() - 进入等待状态...")
    lock.acquire()  # 这里主线程会被阻塞，等待锁释放
    
    print(f"[主线程] 成功获取锁！")
    lock.release()
    
    worker.join()

if __name__ == "__main__":
    main()
