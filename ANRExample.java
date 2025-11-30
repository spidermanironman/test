/**
 * ANR问题示例代码
 * 演示线程sleep被interrupt导致ANR的几种情况
 */

// ========== 错误示例1：主线程上的循环Sleep ==========
public class ANRExample1 {
    private boolean isComplete = false;
    
    // ❌ 危险：在主线程执行会导致ANR
    public void processDataOnMainThread() {
        int count = 0;
        while (!isComplete && count < 10) {
            try {
                Thread.sleep(800);  // 主线程阻塞800ms
                count++;
                // 如果连续7次：800ms × 7 = 5.6秒 > 5秒 → ANR!
            } catch (InterruptedException e) {
                // 问题：没有退出循环，继续sleep
                // 中断状态被清除，但循环继续
                System.out.println("Interrupted but continuing...");
            }
        }
    }
}

// ========== 错误示例2：中断后未恢复中断标志 ==========
public class ANRExample2 extends Thread {
    private volatile boolean running = true;
    
    @Override
    public void run() {
        while (running) {
            try {
                Thread.sleep(800);
                doWork();
            } catch (InterruptedException e) {
                // ❌ 问题1：没有恢复中断状态
                // ❌ 问题2：没有退出循环
                // 如果running仍为true，会再次sleep
                System.out.println("Interrupted");
            }
        }
    }
    
    private void doWork() {
        // 执行某些工作
    }
    
    public void stopThread() {
        running = false;
        interrupt();  // 中断线程
    }
}

// ========== 错误示例3：在关键路径上阻塞 ==========
public class ANRExample3 {
    private final Object lock = new Object();
    
    // ❌ 问题：如果这个线程持有锁，其他线程等待会导致ANR
    public void criticalPath() {
        synchronized (lock) {
            for (int i = 0; i < 10; i++) {
                try {
                    Thread.sleep(800);  // 持有锁时sleep
                    // 其他等待此锁的线程被阻塞
                } catch (InterruptedException e) {
                    // 没有退出，继续持有锁并sleep
                }
            }
        }
    }
}

// ========== 正确示例1：使用Handler（Android主线程） ==========
import android.os.Handler;
import android.os.Looper;

public class CorrectExample1 {
    private Handler handler = new Handler(Looper.getMainLooper());
    
    // ✅ 正确：使用Handler延迟，不阻塞主线程
    public void processDataCorrectly() {
        handler.postDelayed(() -> {
            // 执行操作，不会阻塞主线程
            doWork();
        }, 800);
    }
    
    private void doWork() {
        // 执行某些工作
    }
}

// ========== 正确示例2：正确处理InterruptedException ==========
public class CorrectExample2 extends Thread {
    private volatile boolean running = true;
    
    @Override
    public void run() {
        // ✅ 正确：检查中断状态
        while (!Thread.currentThread().isInterrupted() && running) {
            try {
                Thread.sleep(800);
                doWork();
            } catch (InterruptedException e) {
                // ✅ 正确：恢复中断状态
                Thread.currentThread().interrupt();
                // ✅ 正确：退出循环
                break;
            }
        }
    }
    
    private void doWork() {
        // 执行某些工作
    }
}

// ========== 正确示例3：使用ScheduledExecutorService ==========
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class CorrectExample3 {
    private ScheduledExecutorService executor = 
        Executors.newScheduledThreadPool(1);
    
    // ✅ 正确：使用线程池，不阻塞主线程
    public void scheduleWork() {
        executor.schedule(() -> {
            doWork();
        }, 800, TimeUnit.MILLISECONDS);
    }
    
    private void doWork() {
        // 执行某些工作
    }
    
    public void shutdown() {
        executor.shutdown();
    }
}

// ========== 正确示例4：定期检查中断状态 ==========
public class CorrectExample4 extends Thread {
    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                // ✅ 正确：分段sleep，定期检查中断
                for (int i = 0; i < 8; i++) {
                    if (Thread.currentThread().isInterrupted()) {
                        break;  // 及时响应中断
                    }
                    Thread.sleep(100);  // 每次100ms，总共800ms
                }
                doWork();
            } catch (InterruptedException e) {
                // ✅ 正确：恢复中断状态并退出
                Thread.currentThread().interrupt();
                break;
            }
        }
    }
    
    private void doWork() {
        // 执行某些工作
    }
}
