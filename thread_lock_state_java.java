/**
 * Java中主线程等待锁时的状态演示
 */
public class ThreadLockStateDemo {
    private static final Object lock = new Object();
    
    public static void main(String[] args) {
        System.out.println("=".repeat(50));
        System.out.println("主线程等待锁的状态演示");
        System.out.println("=".repeat(50));
        
        // 工作线程先获取锁
        Thread workerThread = new Thread(() -> {
            synchronized (lock) {
                System.out.println("[工作线程] 已获取锁，持有5秒...");
                try {
                    Thread.sleep(5000);
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
                System.out.println("[工作线程] 释放锁");
            }
        });
        
        workerThread.start();
        
        // 等待一下，确保工作线程先获取锁
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        
        System.out.println("\n[主线程] 尝试获取锁（此时锁已被工作线程持有）...");
        System.out.println("[主线程] 当前状态: " + Thread.currentThread().getState());
        
        // 主线程尝试获取锁，会被阻塞
        System.out.println("[主线程] 调用 synchronized (lock) - 进入等待状态...");
        synchronized (lock) {  // 这里主线程会被阻塞，状态变为 BLOCKED
            System.out.println("[主线程] 成功获取锁！");
        }
        
        // 检查主线程状态
        System.out.println("[主线程] 获取锁后的状态: " + Thread.currentThread().getState());
        
        try {
            workerThread.join();
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
    }
}
