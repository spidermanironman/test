import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.util.Log;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 广播线程状态检查器
 * 用于监控和检查所有处理广播的线程状态
 */
public class BroadcastThreadStatusChecker {
    private static final String TAG = "BroadcastThreadChecker";
    
    // 存储所有广播处理线程的状态
    private static final Map<String, ThreadStatus> threadStatusMap = new ConcurrentHashMap<>();
    
    // 线程状态枚举
    public enum ThreadState {
        NORMAL,      // 正常状态
        BLOCKED,     // 阻塞状态
        WAITING,     // 等待状态
        TIMED_WAITING, // 定时等待状态
        TERMINATED   // 已终止状态
    }
    
    // 线程状态信息
    public static class ThreadStatus {
        public final String threadName;
        public final ThreadState state;
        public final long threadId;
        public final long lastUpdateTime;
        public final String broadcastAction;
        
        public ThreadStatus(String threadName, ThreadState state, long threadId, 
                           String broadcastAction) {
            this.threadName = threadName;
            this.state = state;
            this.threadId = threadId;
            this.lastUpdateTime = System.currentTimeMillis();
            this.broadcastAction = broadcastAction;
        }
        
        public boolean isNormal() {
            return state == ThreadState.NORMAL;
        }
    }
    
    /**
     * 注册广播处理线程
     */
    public static void registerBroadcastThread(String threadName, String broadcastAction) {
        Thread currentThread = Thread.currentThread();
        ThreadState state = getThreadState(currentThread);
        ThreadStatus status = new ThreadStatus(
            threadName, 
            state, 
            currentThread.getId(),
            broadcastAction
        );
        threadStatusMap.put(threadName, status);
        Log.d(TAG, "注册广播线程: " + threadName + ", 状态: " + state);
    }
    
    /**
     * 更新线程状态
     */
    public static void updateThreadStatus(String threadName, ThreadState state) {
        ThreadStatus oldStatus = threadStatusMap.get(threadName);
        if (oldStatus != null) {
            ThreadStatus newStatus = new ThreadStatus(
                oldStatus.threadName,
                state,
                oldStatus.threadId,
                oldStatus.broadcastAction
            );
            threadStatusMap.put(threadName, newStatus);
        }
    }
    
    /**
     * 获取线程状态
     */
    private static ThreadState getThreadState(Thread thread) {
        Thread.State javaState = thread.getState();
        switch (javaState) {
            case NEW:
            case RUNNABLE:
                return ThreadState.NORMAL;
            case BLOCKED:
                return ThreadState.BLOCKED;
            case WAITING:
                return ThreadState.WAITING;
            case TIMED_WAITING:
                return ThreadState.TIMED_WAITING;
            case TERMINATED:
                return ThreadState.TERMINATED;
            default:
                return ThreadState.NORMAL;
        }
    }
    
    /**
     * 检查所有广播处理线程状态是否均正常
     * @return true表示所有线程状态正常，false表示有异常线程
     */
    public static boolean checkAllBroadcastThreadsNormal() {
        List<ThreadStatus> abnormalThreads = new ArrayList<>();
        
        // 遍历所有已注册的线程
        for (Map.Entry<String, ThreadStatus> entry : threadStatusMap.entrySet()) {
            String threadName = entry.getKey();
            ThreadStatus status = entry.getValue();
            
            // 检查线程是否还存在
            Thread thread = findThreadById(status.threadId);
            if (thread == null) {
                Log.w(TAG, "线程不存在: " + threadName);
                abnormalThreads.add(status);
                continue;
            }
            
            // 更新当前状态
            ThreadState currentState = getThreadState(thread);
            if (currentState != ThreadState.NORMAL) {
                Log.w(TAG, "线程状态异常: " + threadName + ", 状态: " + currentState);
                abnormalThreads.add(status);
                updateThreadStatus(threadName, currentState);
            }
        }
        
        if (abnormalThreads.isEmpty()) {
            Log.i(TAG, "✓ 所有广播处理线程状态均正常");
            return true;
        } else {
            Log.e(TAG, "✗ 发现 " + abnormalThreads.size() + " 个异常线程:");
            for (ThreadStatus status : abnormalThreads) {
                Log.e(TAG, "  - " + status.threadName + 
                      " (ID: " + status.threadId + 
                      ", 状态: " + status.state + 
                      ", 广播: " + status.broadcastAction + ")");
            }
            return false;
        }
    }
    
    /**
     * 根据线程ID查找线程
     */
    private static Thread findThreadById(long threadId) {
        ThreadGroup rootGroup = Thread.currentThread().getThreadGroup();
        while (rootGroup.getParent() != null) {
            rootGroup = rootGroup.getParent();
        }
        
        Thread[] threads = new Thread[rootGroup.activeCount() * 2];
        int count = rootGroup.enumerate(threads, true);
        
        for (int i = 0; i < count; i++) {
            if (threads[i].getId() == threadId) {
                return threads[i];
            }
        }
        return null;
    }
    
    /**
     * 获取所有广播线程状态报告
     */
    public static String getThreadStatusReport() {
        StringBuilder report = new StringBuilder();
        report.append("=== 广播线程状态报告 ===\n");
        report.append("总线程数: ").append(threadStatusMap.size()).append("\n\n");
        
        int normalCount = 0;
        for (ThreadStatus status : threadStatusMap.values()) {
            Thread thread = findThreadById(status.threadId);
            ThreadState currentState = thread != null ? getThreadState(thread) : ThreadState.TERMINATED;
            
            if (currentState == ThreadState.NORMAL) {
                normalCount++;
            }
            
            report.append("线程: ").append(status.threadName).append("\n");
            report.append("  ID: ").append(status.threadId).append("\n");
            report.append("  状态: ").append(currentState).append("\n");
            report.append("  广播: ").append(status.broadcastAction).append("\n");
            report.append("  最后更新: ").append(status.lastUpdateTime).append("\n\n");
        }
        
        report.append("正常线程数: ").append(normalCount).append("/").append(threadStatusMap.size()).append("\n");
        report.append("所有线程状态均正常: ").append(normalCount == threadStatusMap.size() ? "是" : "否");
        
        return report.toString();
    }
    
    /**
     * 清除已终止的线程记录
     */
    public static void cleanupTerminatedThreads() {
        List<String> toRemove = new ArrayList<>();
        for (Map.Entry<String, ThreadStatus> entry : threadStatusMap.entrySet()) {
            Thread thread = findThreadById(entry.getValue().threadId);
            if (thread == null || thread.getState() == Thread.State.TERMINATED) {
                toRemove.add(entry.getKey());
            }
        }
        for (String key : toRemove) {
            threadStatusMap.remove(key);
            Log.d(TAG, "清理已终止线程: " + key);
        }
    }
}
