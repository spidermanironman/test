import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.lang.management.ThreadInfo;
import java.util.concurrent.TimeUnit;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

/**
 * 线程状态诊断工具
 * 用于分析线程在runnable和running状态之间的切换情况
 */
public class ThreadStateDiagnostic {
    
    private static final ThreadMXBean threadMXBean = ManagementFactory.getThreadMXBean();
    
    public static void main(String[] args) {
        System.out.println("=== 线程状态诊断工具 ===\n");
        
        // 1. 显示系统信息
        printSystemInfo();
        
        // 2. 创建一些测试线程来观察状态切换
        createTestThreads();
        
        // 3. 监控线程状态
        monitorThreadStates(10); // 监控10秒
    }
    
    /**
     * 打印系统信息
     */
    private static void printSystemInfo() {
        int cpuCores = Runtime.getRuntime().availableProcessors();
        int threadCount = threadMXBean.getThreadCount();
        int peakThreadCount = threadMXBean.getPeakThreadCount();
        
        System.out.println("系统信息:");
        System.out.println("  CPU核心数: " + cpuCores);
        System.out.println("  当前线程数: " + threadCount);
        System.out.println("  峰值线程数: " + peakThreadCount);
        System.out.println("  建议最大线程数: " + (cpuCores * 2) + " (CPU核心数 * 2)");
        System.out.println();
    }
    
    /**
     * 创建测试线程
     */
    private static void createTestThreads() {
        ExecutorService executor = Executors.newFixedThreadPool(4);
        
        // 创建CPU密集型任务
        for (int i = 0; i < 4; i++) {
            final int threadId = i;
            executor.submit(() -> {
                String threadName = "CPU-Intensive-" + threadId;
                Thread.currentThread().setName(threadName);
                
                // CPU密集型计算
                long sum = 0;
                for (long j = 0; j < 1_000_000_000L; j++) {
                    sum += j;
                    // 每1000次循环检查一次中断状态
                    if (j % 1000 == 0 && Thread.currentThread().isInterrupted()) {
                        break;
                    }
                }
                System.out.println(threadName + " 完成计算: " + sum);
            });
        }
        
        // 创建I/O等待任务
        executor.submit(() -> {
            Thread.currentThread().setName("IO-Wait-Thread");
            try {
                // 模拟I/O等待
                for (int i = 0; i < 5; i++) {
                    Thread.sleep(1000);
                    System.out.println("IO-Wait-Thread: 完成I/O操作 " + (i + 1));
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        
        executor.shutdown();
    }
    
    /**
     * 监控线程状态
     */
    private static void monitorThreadStates(long durationSeconds) {
        System.out.println("\n开始监控线程状态 (持续 " + durationSeconds + " 秒)...\n");
        
        long startTime = System.currentTimeMillis();
        long endTime = startTime + TimeUnit.SECONDS.toMillis(durationSeconds);
        
        Map<String, ThreadStateStats> statsMap = new HashMap<>();
        
        int sampleCount = 0;
        while (System.currentTimeMillis() < endTime) {
            sampleCount++;
            ThreadInfo[] threadInfos = threadMXBean.dumpAllThreads(false, false);
            
            // 统计每个线程的状态
            for (ThreadInfo info : threadInfos) {
                String threadName = info.getThreadName();
                Thread.State state = info.getThreadState();
                long cpuTime = threadMXBean.getThreadCpuTime(info.getThreadId());
                
                ThreadStateStats stats = statsMap.computeIfAbsent(
                    threadName, 
                    k -> new ThreadStateStats(threadName)
                );
                
                stats.recordState(state, cpuTime);
            }
            
            // 每5秒打印一次快照
            if (sampleCount % 5 == 0) {
                printSnapshot(threadInfos);
            }
            
            try {
                Thread.sleep(1000); // 每秒采样一次
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        
        // 打印统计结果
        printStatistics(statsMap);
    }
    
    /**
     * 打印线程状态快照
     */
    private static void printSnapshot(ThreadInfo[] threadInfos) {
        System.out.println("\n=== 线程状态快照 ===");
        System.out.printf("%-30s %-15s %-20s %s%n", 
            "线程名", "状态", "CPU时间(ns)", "阻塞次数");
        
        for (ThreadInfo info : threadInfos) {
            long cpuTime = threadMXBean.getThreadCpuTime(info.getThreadId());
            System.out.printf("%-30s %-15s %-20d %d%n",
                info.getThreadName(),
                info.getThreadState(),
                cpuTime,
                info.getBlockedCount());
        }
    }
    
    /**
     * 打印统计结果
     */
    private static void printStatistics(Map<String, ThreadStateStats> statsMap) {
        System.out.println("\n\n=== 线程状态统计 ===");
        System.out.printf("%-30s %-15s %-15s %-20s%n",
            "线程名", "RUNNABLE次数", "其他状态次数", "总CPU时间(ns)");
        
        for (ThreadStateStats stats : statsMap.values()) {
            System.out.printf("%-30s %-15d %-15d %-20d%n",
                stats.threadName,
                stats.runnableCount,
                stats.otherStateCount,
                stats.totalCpuTime);
        }
        
        // 诊断建议
        System.out.println("\n=== 诊断建议 ===");
        int cpuCores = Runtime.getRuntime().availableProcessors();
        int threadCount = threadMXBean.getThreadCount();
        
        if (threadCount > cpuCores * 4) {
            System.out.println("⚠️  警告: 线程数过多 (" + threadCount + 
                " > " + (cpuCores * 4) + ")");
            System.out.println("   建议: 减少线程数或使用线程池限制线程数量");
        }
        
        long totalCpuTime = statsMap.values().stream()
            .mapToLong(s -> s.totalCpuTime)
            .sum();
        
        if (totalCpuTime > 0) {
            System.out.println("✓ CPU时间统计正常");
        }
    }
    
    /**
     * 线程状态统计类
     */
    static class ThreadStateStats {
        String threadName;
        int runnableCount = 0;
        int otherStateCount = 0;
        long totalCpuTime = 0;
        long lastCpuTime = 0;
        
        ThreadStateStats(String threadName) {
            this.threadName = threadName;
        }
        
        void recordState(Thread.State state, long cpuTime) {
            if (state == Thread.State.RUNNABLE) {
                runnableCount++;
            } else {
                otherStateCount++;
            }
            
            // 计算CPU时间增量
            if (cpuTime > lastCpuTime) {
                totalCpuTime += (cpuTime - lastCpuTime);
                lastCpuTime = cpuTime;
            }
        }
    }
}
