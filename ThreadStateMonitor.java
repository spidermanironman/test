import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 线程状态监控工具
 * 用于诊断线程状态频繁切换的问题
 */
public class ThreadStateMonitor {
    private static final ThreadMXBean threadMXBean = ManagementFactory.getThreadMXBean();
    private static final AtomicLong lastCheckTime = new AtomicLong(System.currentTimeMillis());
    
    public static void main(String[] args) {
        System.out.println("=== 线程状态监控工具 ===");
        System.out.println("监控线程状态变化，按Ctrl+C退出\n");
        
        // 启动一个测试线程来观察状态变化
        Thread testThread = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                // 模拟一些工作
                doWork();
                // 短暂休眠，模拟等待
                try {
                    Thread.sleep(10);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "TestWorker");
        
        testThread.start();
        
        // 监控线程状态
        monitorThreadState(testThread, 1000); // 监控1秒
        
        testThread.interrupt();
        try {
            testThread.join();
        } catch (InterruptedException e) {
            e.printStackTrace();
        }
    }
    
    /**
     * 模拟工作负载
     */
    private static void doWork() {
        // CPU密集型工作
        for (int i = 0; i < 100000; i++) {
            Math.sqrt(i);
        }
    }
    
    /**
     * 监控指定线程的状态变化
     */
    public static void monitorThreadState(Thread thread, long durationMs) {
        long startTime = System.currentTimeMillis();
        long endTime = startTime + durationMs;
        
        Thread.State lastState = null;
        long stateChangeCount = 0;
        long[] stateDurations = new long[Thread.State.values().length];
        long[] stateCounts = new long[Thread.State.values().length];
        
        System.out.println("开始监控线程: " + thread.getName());
        System.out.println("线程ID: " + thread.getId());
        System.out.println("监控时长: " + durationMs + "ms\n");
        
        while (System.currentTimeMillis() < endTime) {
            Thread.State currentState = thread.getState();
            long currentTime = System.currentTimeMillis();
            
            if (lastState != null && currentState != lastState) {
                stateChangeCount++;
                long duration = currentTime - lastCheckTime.get();
                
                System.out.printf("[%dms] 状态变化: %s -> %s (持续时间: %dms)\n",
                    currentTime - startTime,
                    lastState,
                    currentState,
                    duration);
                
                // 记录状态持续时间
                if (lastState.ordinal() < stateDurations.length) {
                    stateDurations[lastState.ordinal()] += duration;
                    stateCounts[lastState.ordinal()]++;
                }
            }
            
            lastState = currentState;
            lastCheckTime.set(currentTime);
            
            try {
                Thread.sleep(1); // 每1ms检查一次
            } catch (InterruptedException e) {
                break;
            }
        }
        
        // 打印统计信息
        printStatistics(stateChangeCount, stateDurations, stateCounts, durationMs);
        
        // 打印详细线程信息
        printThreadInfo(thread.getId());
    }
    
    /**
     * 打印统计信息
     */
    private static void printStatistics(long stateChangeCount, long[] stateDurations, 
                                       long[] stateCounts, long totalDuration) {
        System.out.println("\n=== 统计信息 ===");
        System.out.println("总状态变化次数: " + stateChangeCount);
        System.out.println("平均状态变化频率: " + 
            (stateChangeCount * 1000.0 / totalDuration) + " 次/秒");
        System.out.println("\n各状态统计:");
        
        Thread.State[] states = Thread.State.values();
        for (int i = 0; i < states.length; i++) {
            if (stateCounts[i] > 0) {
                double avgDuration = stateDurations[i] / (double) stateCounts[i];
                double percentage = (stateDurations[i] * 100.0) / totalDuration;
                System.out.printf("  %s: 出现%d次, 平均持续时间: %.2fms, 总占比: %.2f%%\n",
                    states[i], stateCounts[i], avgDuration, percentage);
            }
        }
    }
    
    /**
     * 打印线程详细信息
     */
    private static void printThreadInfo(long threadId) {
        System.out.println("\n=== 线程详细信息 ===");
        ThreadInfo threadInfo = threadMXBean.getThreadInfo(threadId);
        if (threadInfo != null) {
            System.out.println("线程名: " + threadInfo.getThreadName());
            System.out.println("线程状态: " + threadInfo.getThreadState());
            System.out.println("阻塞次数: " + threadInfo.getBlockedCount());
            System.out.println("等待次数: " + threadInfo.getWaitedCount());
            System.out.println("CPU时间: " + 
                (threadMXBean.getThreadCpuTime(threadId) / 1_000_000) + "ms");
            
            if (threadInfo.getLockName() != null) {
                System.out.println("等待的锁: " + threadInfo.getLockName());
            }
            
            if (threadInfo.getLockOwnerName() != null) {
                System.out.println("锁持有者: " + threadInfo.getLockOwnerName());
            }
        }
        
        // 系统信息
        System.out.println("\n=== 系统信息 ===");
        System.out.println("CPU核心数: " + Runtime.getRuntime().availableProcessors());
        System.out.println("活动线程数: " + threadMXBean.getThreadCount());
        System.out.println("峰值线程数: " + threadMXBean.getPeakThreadCount());
    }
}
