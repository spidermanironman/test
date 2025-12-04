import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.lang.management.ThreadInfo;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.concurrent.locks.Lock;

/**
 * 解决线程频繁切换问题的示例代码
 */
public class 解决方案示例 {
    
    public static void main(String[] args) {
        System.out.println("=== 线程优化示例 ===\n");
        
        // 方案1: 使用合适的线程池大小
        demonstrateOptimalThreadPool();
        
        // 方案2: 使用异步I/O减少等待
        demonstrateAsyncIO();
        
        // 方案3: 减少锁竞争
        demonstrateLockOptimization();
    }
    
    /**
     * 方案1: 使用合适的线程池大小
     * 线程数 = CPU核心数 + I/O等待时间 / CPU计算时间
     */
    private static void demonstrateOptimalThreadPool() {
        System.out.println("方案1: 优化线程池大小");
        
        int cpuCores = Runtime.getRuntime().availableProcessors();
        
        // CPU密集型任务: 线程数 = CPU核心数 + 1
        ExecutorService cpuIntensivePool = Executors.newFixedThreadPool(cpuCores + 1);
        
        // I/O密集型任务: 线程数 = CPU核心数 * 2
        ExecutorService ioIntensivePool = Executors.newFixedThreadPool(cpuCores * 2);
        
        // 混合任务: 使用自定义线程池
        ThreadPoolExecutor mixedPool = new ThreadPoolExecutor(
            cpuCores,                    // 核心线程数
            cpuCores * 2,                // 最大线程数
            60L,                         // 空闲线程存活时间
            TimeUnit.SECONDS,
            new LinkedBlockingQueue<>(100), // 工作队列
            new ThreadFactory() {
                private int count = 0;
                @Override
                public Thread newThread(Runnable r) {
                    Thread t = new Thread(r, "OptimizedThread-" + (count++));
                    t.setPriority(Thread.NORM_PRIORITY);
                    return t;
                }
            },
            new ThreadPoolExecutor.CallerRunsPolicy() // 拒绝策略
        );
        
        System.out.println("  CPU核心数: " + cpuCores);
        System.out.println("  CPU密集型线程池大小: " + (cpuCores + 1));
        System.out.println("  I/O密集型线程池大小: " + (cpuCores * 2));
        System.out.println();
    }
    
    /**
     * 方案2: 使用异步I/O减少线程等待
     */
    private static void demonstrateAsyncIO() {
        System.out.println("方案2: 使用异步I/O");
        
        // 使用CompletableFuture进行异步操作
        CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
            // 模拟I/O操作
            try {
                Thread.sleep(1000); // 模拟网络请求
                return "数据加载完成";
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return "操作被中断";
            }
        });
        
        // 不阻塞主线程，继续执行其他操作
        System.out.println("  主线程继续执行其他任务...");
        
        // 异步处理结果
        future.thenAccept(result -> {
            System.out.println("  异步结果: " + result);
        });
        
        System.out.println("  使用CompletableFuture可以避免线程阻塞等待I/O");
        System.out.println();
    }
    
    /**
     * 方案3: 减少锁竞争
     */
    private static void demonstrateLockOptimization() {
        System.out.println("方案3: 减少锁竞争");
        
        // 使用无锁数据结构
        AtomicLong counter = new AtomicLong(0);
        
        // 多个线程并发更新，无需加锁
        ExecutorService executor = Executors.newFixedThreadPool(4);
        for (int i = 0; i < 10; i++) {
            executor.submit(() -> {
                for (int j = 0; j < 1000; j++) {
                    counter.incrementAndGet(); // 无锁操作
                }
            });
        }
        
        executor.shutdown();
        try {
            executor.awaitTermination(5, TimeUnit.SECONDS);
            System.out.println("  无锁计数器最终值: " + counter.get());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        
        // 使用读写锁减少锁竞争
        ReadWriteLock readWriteLock = new ReentrantReadWriteLock();
        Lock readLock = readWriteLock.readLock();
        Lock writeLock = readWriteLock.writeLock();
        
        System.out.println("  使用ReadWriteLock: 多个读操作可以并发执行");
        System.out.println("  使用AtomicLong等无锁数据结构: 避免锁竞争");
        System.out.println();
    }
    
    /**
     * 方案4: 使用工作窃取线程池（适合任务执行时间差异大的场景）
     */
    public static void demonstrateWorkStealingPool() {
        System.out.println("方案4: 使用工作窃取线程池");
        
        // ForkJoinPool使用工作窃取算法，可以减少线程等待时间
        ForkJoinPool forkJoinPool = new ForkJoinPool(
            Runtime.getRuntime().availableProcessors(),
            ForkJoinPool.defaultForkJoinWorkerThreadFactory,
            null,
            true // 异步模式
        );
        
        System.out.println("  ForkJoinPool使用工作窃取算法，适合任务执行时间差异大的场景");
        System.out.println();
    }
    
    /**
     * 方案5: 监控和调优
     */
    public static void demonstrateMonitoring() {
        System.out.println("方案5: 监控线程状态");
        
        ThreadMXBean threadMXBean = ManagementFactory.getThreadMXBean();
        
        // 启用线程CPU时间测量
        if (threadMXBean.isThreadCpuTimeSupported()) {
            threadMXBean.setThreadCpuTimeEnabled(true);
        }
        
        // 定期检查线程状态
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);
        scheduler.scheduleAtFixedRate(() -> {
            ThreadInfo[] threads = threadMXBean.dumpAllThreads(false, false);
            long runnableCount = Arrays.stream(threads)
                .filter(t -> t.getThreadState() == Thread.State.RUNNABLE)
                .count();
            
            System.out.println("  当前RUNNABLE状态线程数: " + runnableCount + 
                             " / " + threads.length);
        }, 0, 5, TimeUnit.SECONDS);
        
        System.out.println("  定期监控可以帮助发现线程状态异常");
    }
}
