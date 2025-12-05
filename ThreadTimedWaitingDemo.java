/**
 * 演示线程 TIMED_WAITING 状态
 * 
 * 重要说明：
 * 线程不会"等待多久后"才进入 TIMED_WAITING 状态
 * 而是在调用带超时参数的方法时，立即进入 TIMED_WAITING 状态
 */
public class ThreadTimedWaitingDemo {
    
    public static void main(String[] args) throws InterruptedException {
        System.out.println("=== 线程 TIMED_WAITING 状态演示 ===\n");
        
        // 演示1: Thread.sleep() - 立即进入 TIMED_WAITING
        demonstrateThreadSleep();
        
        // 演示2: Object.wait(timeout) - 立即进入 TIMED_WAITING
        demonstrateObjectWait();
        
        // 演示3: Thread.join(timeout) - 立即进入 TIMED_WAITING
        demonstrateThreadJoin();
    }
    
    /**
     * 演示 Thread.sleep() 立即进入 TIMED_WAITING 状态
     */
    private static void demonstrateThreadSleep() throws InterruptedException {
        System.out.println("1. Thread.sleep() 示例:");
        Thread thread = new Thread(() -> {
            try {
                System.out.println("  线程开始 sleep(5000ms)");
                Thread.sleep(5000); // 立即进入 TIMED_WAITING 状态
                System.out.println("  线程 sleep 结束");
            } catch (InterruptedException e) {
                System.out.println("  线程被中断");
            }
        });
        
        thread.start();
        Thread.sleep(100); // 等待线程启动
        
        System.out.println("  线程状态: " + thread.getState());
        System.out.println("  ✓ 线程在调用 sleep() 后立即进入 TIMED_WAITING 状态\n");
        
        thread.join();
    }
    
    /**
     * 演示 Object.wait(timeout) 立即进入 TIMED_WAITING 状态
     */
    private static void demonstrateObjectWait() throws InterruptedException {
        System.out.println("2. Object.wait(timeout) 示例:");
        Object lock = new Object();
        
        Thread thread = new Thread(() -> {
            synchronized (lock) {
                try {
                    System.out.println("  线程开始 wait(3000ms)");
                    lock.wait(3000); // 立即进入 TIMED_WAITING 状态
                    System.out.println("  线程 wait 结束");
                } catch (InterruptedException e) {
                    System.out.println("  线程被中断");
                }
            }
        });
        
        thread.start();
        Thread.sleep(100); // 等待线程启动并获取锁
        
        System.out.println("  线程状态: " + thread.getState());
        System.out.println("  ✓ 线程在调用 wait(timeout) 后立即进入 TIMED_WAITING 状态\n");
        
        thread.join();
    }
    
    /**
     * 演示 Thread.join(timeout) 立即进入 TIMED_WAITING 状态
     */
    private static void demonstrateThreadJoin() throws InterruptedException {
        System.out.println("3. Thread.join(timeout) 示例:");
        
        Thread workerThread = new Thread(() -> {
            try {
                System.out.println("  工作线程运行中...");
                Thread.sleep(2000);
                System.out.println("  工作线程完成");
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        });
        
        workerThread.start();
        
        Thread mainThread = Thread.currentThread();
        Thread monitorThread = new Thread(() -> {
            try {
                Thread.sleep(50);
                System.out.println("  主线程调用 join(4000ms)");
                workerThread.join(4000); // 立即进入 TIMED_WAITING 状态
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        });
        
        monitorThread.start();
        Thread.sleep(100);
        
        System.out.println("  监控线程状态: " + monitorThread.getState());
        System.out.println("  ✓ 线程在调用 join(timeout) 后立即进入 TIMED_WAITING 状态\n");
        
        monitorThread.join();
        workerThread.join();
    }
}
