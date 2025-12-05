import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 监控线程TIMED_WAITING状态的持续时间
 * 当线程在TIMED_WAITING状态超过指定阈值时，会上报
 */
public class ThreadTimeWaitingMonitor {
    
    private final ThreadMXBean threadMXBean;
    private final ConcurrentHashMap<Long, Long> threadStateStartTime = new ConcurrentHashMap<>();
    private final long reportThresholdMs; // 上报阈值（毫秒）
    private final ScheduledExecutorService scheduler;
    
    /**
     * @param reportThresholdMs 线程在TIMED_WAITING状态持续多少毫秒后上报
     * @param checkIntervalMs 检查间隔（毫秒）
     */
    public ThreadTimeWaitingMonitor(long reportThresholdMs, long checkIntervalMs) {
        this.threadMXBean = ManagementFactory.getThreadMXBean();
        this.reportThresholdMs = reportThresholdMs;
        this.scheduler = Executors.newScheduledThreadPool(1);
        
        // 定期检查线程状态
        scheduler.scheduleAtFixedRate(
            this::checkAndReport,
            0,
            checkIntervalMs,
            TimeUnit.MILLISECONDS
        );
    }
    
    private void checkAndReport() {
        long[] threadIds = threadMXBean.getAllThreadIds();
        ThreadInfo[] threadInfos = threadMXBean.getThreadInfo(threadIds);
        
        long currentTime = System.currentTimeMillis();
        
        for (ThreadInfo threadInfo : threadInfos) {
            if (threadInfo == null) continue;
            
            long threadId = threadInfo.getThreadId();
            Thread.State state = threadInfo.getThreadState();
            
            if (state == Thread.State.TIMED_WAITING) {
                // 线程当前处于TIMED_WAITING状态
                Long startTime = threadStateStartTime.get(threadId);
                
                if (startTime == null) {
                    // 刚进入TIMED_WAITING状态，记录开始时间
                    threadStateStartTime.put(threadId, currentTime);
                } else {
                    // 已经在TIMED_WAITING状态，计算持续时间
                    long duration = currentTime - startTime;
                    
                    if (duration >= reportThresholdMs) {
                        // 超过阈值，上报
                        reportTimeWaitingThread(threadInfo, duration);
                        // 重置开始时间，避免重复上报
                        threadStateStartTime.put(threadId, currentTime);
                    }
                }
            } else {
                // 线程不在TIMED_WAITING状态，清除记录
                threadStateStartTime.remove(threadId);
            }
        }
    }
    
    private void reportTimeWaitingThread(ThreadInfo threadInfo, long duration) {
        System.out.println(String.format(
            "[TIMED_WAITING Report] Thread: %s (ID: %d) has been in TIMED_WAITING state for %d ms (%.2f seconds)\n" +
            "  Stack trace:\n%s",
            threadInfo.getThreadName(),
            threadInfo.getThreadId(),
            duration,
            duration / 1000.0,
            getStackTrace(threadInfo)
        ));
    }
    
    private String getStackTrace(ThreadInfo threadInfo) {
        StringBuilder sb = new StringBuilder();
        StackTraceElement[] stackTrace = threadInfo.getStackTrace();
        for (int i = 0; i < Math.min(stackTrace.length, 10); i++) {
            sb.append("    at ").append(stackTrace[i]).append("\n");
        }
        return sb.toString();
    }
    
    public void shutdown() {
        scheduler.shutdown();
    }
    
    /**
     * 示例用法
     */
    public static void main(String[] args) throws InterruptedException {
        // 创建监控器：线程在TIMED_WAITING状态超过5秒后上报，每1秒检查一次
        ThreadTimeWaitingMonitor monitor = new ThreadTimeWaitingMonitor(5000, 1000);
        
        // 创建一个测试线程，让它进入TIMED_WAITING状态
        Thread testThread = new Thread(() -> {
            try {
                System.out.println("Test thread entering TIMED_WAITING for 10 seconds...");
                Thread.sleep(10000); // 睡眠10秒
                System.out.println("Test thread woke up");
            } catch (InterruptedException e) {
                e.printStackTrace();
            }
        }, "TestThread");
        
        testThread.start();
        
        // 等待一段时间让监控器有机会上报
        Thread.sleep(15000);
        
        monitor.shutdown();
    }
}
