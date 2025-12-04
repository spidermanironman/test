import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 线程状态分析示例
 * 演示可能导致线程状态频繁切换的几种场景
 */
public class ThreadStateAnalysis {
    
    public static void main(String[] args) throws InterruptedException {
        System.out.println("=== 线程状态频繁切换场景分析 ===\n");
        
        // 场景1: CPU密集型任务 + 多线程竞争
        System.out.println("场景1: CPU密集型任务 + 多线程竞争");
        scenario1_CPUIntensive();
        
        Thread.sleep(2000);
        
        // 场景2: 频繁的锁竞争
        System.out.println("\n场景2: 频繁的锁竞争");
        scenario2_LockContention();
        
        Thread.sleep(2000);
        
        // 场景3: 频繁的I/O操作
        System.out.println("\n场景3: 频繁的I/O操作");
        scenario3_FrequentIO();
        
        Thread.sleep(2000);
        
        // 场景4: 线程数过多
        System.out.println("\n场景4: 线程数过多（超过CPU核心数）");
        scenario4_TooManyThreads();
    }
    
    /**
     * 场景1: CPU密集型任务 + 多线程竞争
     * 现象: 线程频繁在RUNNABLE状态切换，因为时间片轮转
     */
    private static void scenario1_CPUIntensive() {
        int threadCount = Runtime.getRuntime().availableProcessors() * 2;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch latch = new CountDownLatch(threadCount);
        
        System.out.println("创建 " + threadCount + " 个线程执行CPU密集型任务");
        System.out.println("CPU核心数: " + Runtime.getRuntime().availableProcessors());
        System.out.println("线程数 > CPU核心数，会导致频繁的线程切换\n");
        
        for (int i = 0; i < threadCount; i++) {
            final int id = i;
            executor.submit(() -> {
                try {
                    // CPU密集型工作
                    long sum = 0;
                    for (int j = 0; j < 10_000_000; j++) {
                        sum += Math.sqrt(j);
                    }
                    System.out.println("线程 " + id + " 完成，结果: " + sum);
                } finally {
                    latch.countDown();
                }
            });
        }
        
        try {
            latch.await(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        
        executor.shutdown();
    }
    
    /**
     * 场景2: 频繁的锁竞争
     * 现象: 线程频繁在RUNNABLE和BLOCKED状态之间切换
     */
    private static void scenario2_LockContention() {
        final Object lock = new Object();
        final AtomicInteger counter = new AtomicInteger(0);
        int threadCount = 10;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch latch = new CountDownLatch(threadCount);
        
        System.out.println("创建 " + threadCount + " 个线程竞争同一个锁");
        System.out.println("每个线程频繁获取/释放锁，导致状态频繁切换\n");
        
        for (int i = 0; i < threadCount; i++) {
            executor.submit(() -> {
                try {
                    for (int j = 0; j < 1000; j++) {
                        synchronized (lock) {
                            // 持有锁的时间很短
                            counter.incrementAndGet();
                            // 没有sleep，立即释放锁
                        }
                        // 释放锁后，其他线程可以竞争
                    }
                } finally {
                    latch.countDown();
                }
            });
        }
        
        try {
            latch.await(5, TimeUnit.SECONDS);
            System.out.println("最终计数: " + counter.get());
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        
        executor.shutdown();
    }
    
    /**
     * 场景3: 频繁的I/O操作
     * 现象: 线程在RUNNABLE和WAITING/TIMED_WAITING状态之间切换
     */
    private static void scenario3_FrequentIO() {
        int threadCount = 20;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch latch = new CountDownLatch(threadCount);
        
        System.out.println("创建 " + threadCount + " 个线程执行频繁的I/O操作（模拟）");
        System.out.println("每次I/O操作后线程会进入等待状态\n");
        
        for (int i = 0; i < threadCount; i++) {
            final int id = i;
            executor.submit(() -> {
                try {
                    for (int j = 0; j < 100; j++) {
                        // 模拟I/O操作
                        Thread.sleep(1); // 模拟I/O等待
                        // 短暂工作
                        Math.sqrt(j);
                    }
                    System.out.println("线程 " + id + " 完成I/O操作");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    latch.countDown();
                }
            });
        }
        
        try {
            latch.await(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        
        executor.shutdown();
    }
    
    /**
     * 场景4: 线程数过多
     * 现象: 大量线程竞争有限的CPU资源，导致频繁切换
     */
    private static void scenario4_TooManyThreads() {
        int cpuCores = Runtime.getRuntime().availableProcessors();
        int threadCount = cpuCores * 10; // 线程数是CPU核心数的10倍
        
        System.out.println("CPU核心数: " + cpuCores);
        System.out.println("创建 " + threadCount + " 个线程（线程数 >> CPU核心数）");
        System.out.println("这会导致严重的线程切换开销\n");
        
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch latch = new CountDownLatch(threadCount);
        
        for (int i = 0; i < threadCount; i++) {
            final int id = i;
            executor.submit(() -> {
                try {
                    // 每个线程做少量工作
                    long sum = 0;
                    for (int j = 0; j < 1_000_000; j++) {
                        sum += j;
                    }
                    if (id < 5) { // 只打印前5个
                        System.out.println("线程 " + id + " 完成");
                    }
                } finally {
                    latch.countDown();
                }
            });
        }
        
        try {
            latch.await(5, TimeUnit.SECONDS);
            System.out.println("所有线程完成");
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
        
        executor.shutdown();
    }
}
