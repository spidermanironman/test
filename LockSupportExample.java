import java.util.concurrent.locks.LockSupport;

/**
 * LockSupport.parkNanos() 方法详解和示例
 * 
 * LockSupport 是 Java 并发包中用于线程阻塞和唤醒的基础工具类
 * parkNanos() 方法用于让当前线程暂停指定的纳秒数
 */
public class LockSupportExample {
    
    /**
     * LockSupport.parkNanos(timeout) 的作用：
     * 
     * 1. 功能：让当前线程暂停（阻塞）指定的纳秒数
     * 2. 参数：timeout - 暂停的纳秒数（1秒 = 1,000,000,000 纳秒）
     * 3. 状态：调用后线程会进入 TIMED_WAITING 状态
     * 4. 唤醒：时间到期后自动唤醒，或者可以被其他线程通过 unpark() 提前唤醒
     * 
     * 与其他方法的区别：
     * - Thread.sleep(): 只能等待固定时间，不能被提前唤醒
     * - Object.wait(): 必须在 synchronized 块中使用，需要配合 notify()
     * - LockSupport.parkNanos(): 更底层，不需要锁，可以被 unpark() 提前唤醒
     */
    
    public static void main(String[] args) throws InterruptedException {
        System.out.println("=== LockSupport.parkNanos() 示例 ===\n");
        
        // 示例1：基本用法 - 暂停5秒
        example1_BasicUsage();
        
        Thread.sleep(6000);
        
        // 示例2：可以被提前唤醒
        example2_Interruptible();
        
        Thread.sleep(6000);
        
        // 示例3：与其他方法的对比
        example3_Comparison();
    }
    
    /**
     * 示例1：基本用法
     * 线程会暂停指定的纳秒数
     */
    private static void example1_BasicUsage() {
        System.out.println("示例1：基本用法 - 暂停5秒");
        System.out.println("开始时间: " + System.currentTimeMillis());
        
        // 暂停 5 秒 = 5 * 1,000,000,000 纳秒
        long nanos = 5_000_000_000L; // 5秒
        LockSupport.parkNanos(nanos);
        
        System.out.println("结束时间: " + System.currentTimeMillis());
        System.out.println("线程已恢复执行\n");
    }
    
    /**
     * 示例2：可以被提前唤醒
     * 通过另一个线程调用 unpark() 可以提前唤醒被 park 的线程
     */
    private static void example2_Interruptible() {
        System.out.println("示例2：可以被提前唤醒");
        
        Thread targetThread = Thread.currentThread();
        
        // 创建一个线程，在2秒后唤醒主线程
        Thread wakerThread = new Thread(() -> {
            try {
                Thread.sleep(2000); // 等待2秒
                System.out.println("Waker线程：准备唤醒目标线程");
                LockSupport.unpark(targetThread); // 提前唤醒
                System.out.println("Waker线程：已调用 unpark()");
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        });
        
        wakerThread.start();
        
        System.out.println("主线程：准备暂停10秒");
        long startTime = System.currentTimeMillis();
        
        // 尝试暂停10秒，但会被提前唤醒
        LockSupport.parkNanos(10_000_000_000L); // 10秒
        
        long endTime = System.currentTimeMillis();
        System.out.println("主线程：已恢复，实际暂停了 " + (endTime - startTime) + " 毫秒");
        System.out.println("（被提前唤醒，而不是等待10秒）\n");
    }
    
    /**
     * 示例3：与其他方法的对比
     */
    private static void example3_Comparison() {
        System.out.println("示例3：parkNanos vs Thread.sleep");
        
        // 使用 parkNanos
        long start1 = System.nanoTime();
        LockSupport.parkNanos(1_000_000_000L); // 1秒
        long end1 = System.nanoTime();
        System.out.println("parkNanos(1秒) 实际耗时: " + (end1 - start1) / 1_000_000 + " 毫秒");
        
        // 使用 Thread.sleep
        try {
            long start2 = System.nanoTime();
            Thread.sleep(1000); // 1秒
            long end2 = System.nanoTime();
            System.out.println("Thread.sleep(1秒) 实际耗时: " + (end2 - start2) / 1_000_000 + " 毫秒");
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        
        System.out.println("\n注意：两者功能类似，但 parkNanos 更底层，可以被 unpark() 提前唤醒");
    }
}

/**
 * 实际应用场景：
 * 
 * 1. 自旋锁优化：在自旋等待时，可以使用 parkNanos 短暂暂停，避免 CPU 空转
 * 2. 条件等待：实现自定义的等待/通知机制
 * 3. 并发工具类：Java 的 AQS (AbstractQueuedSynchronizer) 底层就使用了 LockSupport
 * 4. 线程池：某些线程池实现中用于工作线程的等待
 * 
 * 示例：自旋锁中使用 parkNanos
 */
class SpinLockWithParkNanos {
    private volatile boolean locked = false;
    
    public void lock() {
        // 自旋尝试获取锁
        while (!tryLock()) {
            // 如果获取失败，短暂暂停，避免 CPU 空转
            LockSupport.parkNanos(1000L); // 暂停 1000 纳秒（1微秒）
        }
    }
    
    private boolean tryLock() {
        if (!locked) {
            locked = true;
            return true;
        }
        return false;
    }
    
    public void unlock() {
        locked = false;
        // 可以唤醒等待的线程
        // LockSupport.unpark(waitingThread);
    }
}
