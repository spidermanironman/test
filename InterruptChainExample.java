/**
 * InterruptedException处理责任链示例
 * 演示"接力"机制：谁应该处理中断异常
 */

// ========== 场景1：Worker线程自己"接力" ==========
public class WorkerThreadExample extends Thread {
    private volatile boolean running = true;
    
    @Override
    public void run() {
        // ✅ Worker线程自己负责处理中断
        // 因为它在自己的run()方法中调用sleep
        while (running && !isInterrupted()) {
            try {
                Thread.sleep(800);  // Worker线程调用
                doWork();
            } catch (InterruptedException e) {
                // ✅ Worker线程"接力"处理
                // 1. 恢复中断状态
                Thread.currentThread().interrupt();
                // 2. 退出循环
                break;
            }
        }
    }
    
    private void doWork() {
        System.out.println("Working...");
    }
    
    public void stopWorker() {
        running = false;
        interrupt();  // 中断Worker线程
    }
}

// ========== 场景2：业务层委托，工具类"接力" ==========
// 业务层：不应该直接处理sleep
public class BusinessService {
    private DelayUtil delayUtil = new DelayUtil();
    
    // ✅ 业务层委托给工具类
    public void processBusinessLogic() {
        delayUtil.delay(800);  // 委托，不直接处理中断
        // 继续业务逻辑
    }
}

// 工具类：负责"接力"处理中断
public class DelayUtil {
    // ✅ 工具类负责处理中断
    public void delay(long milliseconds) {
        try {
            Thread.sleep(milliseconds);
        } catch (InterruptedException e) {
            // ✅ 工具类"接力"处理
            Thread.currentThread().interrupt();
            // 转换为运行时异常，因为业务层不应该处理中断
            throw new RuntimeException("Delay interrupted", e);
        }
    }
}

// ========== 场景3：框架层传播，应用层"接力" ==========
// 框架层：不知道业务逻辑，传播异常
public class FrameworkUtil {
    // ✅ 框架层传播异常，让调用者决定如何处理
    public void frameworkDelay(long ms) throws InterruptedException {
        Thread.sleep(ms);
        // 框架不知道如何处理中断，传播给应用层
    }
}

// 应用层：必须"接力"处理
public class Application {
    private FrameworkUtil framework = new FrameworkUtil();
    
    // ✅ 应用层最终"接力"处理
    public void applicationMethod() {
        try {
            framework.frameworkDelay(800);
        } catch (InterruptedException e) {
            // ✅ 应用层"接力"处理
            Thread.currentThread().interrupt();
            handleInterruption();  // 应用层知道如何处理
        }
    }
    
    private void handleInterruption() {
        // 应用层知道如何清理和恢复
        System.out.println("Application interrupted, cleaning up...");
    }
}

// ========== 场景4：ExecutorService任务自己"接力" ==========
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorServiceExample {
    private ExecutorService executor = Executors.newFixedThreadPool(1);
    
    public void submitTask() {
        // ✅ 任务自己"接力"处理中断
        Future<?> future = executor.submit(() -> {
            try {
                Thread.sleep(800);
                doWork();
            } catch (InterruptedException e) {
                // ✅ 任务自己"接力"处理
                Thread.currentThread().interrupt();
                System.out.println("Task interrupted, exiting");
                return;  // 退出任务
            }
        });
        
        // 如果需要取消任务
        // future.cancel(true);  // interrupt = true
    }
    
    private void doWork() {
        System.out.println("Task working...");
    }
}

// ========== 场景5：多层调用链中的"接力" ==========
public class MultiLayerExample {
    
    // 第1层：底层方法，抛出异常
    public void layer1() throws InterruptedException {
        Thread.sleep(800);  // 抛出InterruptedException
    }
    
    // 第2层：中层方法，可以传播
    public void layer2() throws InterruptedException {
        layer1();  // ✅ 传播异常，让上层处理
    }
    
    // 第3层：中层方法，也可以传播
    public void layer3() throws InterruptedException {
        layer2();  // ✅ 继续传播
    }
    
    // 第4层：顶层方法，必须"接力"处理
    public void layer4() {
        try {
            layer3();  // 不能再传播了
        } catch (InterruptedException e) {
            // ✅ 顶层方法必须"接力"处理
            Thread.currentThread().interrupt();
            handleTopLevelInterruption();
        }
    }
    
    private void handleTopLevelInterruption() {
        System.out.println("Top level interruption handled");
    }
}

// ========== 错误示例：没有"接力"处理 ==========
public class WrongExample {
    private boolean condition = true;
    
    // ❌ 错误：没有"接力"处理，导致ANR
    public void wrongMethod() {
        int count = 0;
        while (condition && count < 10) {
            try {
                Thread.sleep(800);  // 被interrupt后
                count++;
            } catch (InterruptedException e) {
                // ❌ 问题：没有"接力"处理
                // 1. 没有恢复中断状态
                // 2. 没有退出循环
                // 3. 继续sleep，累积阻塞时间 → ANR
                System.out.println("Interrupted but continuing...");
            }
        }
    }
}

// ========== 正确示例：正确"接力"处理 ==========
public class CorrectExample {
    private boolean condition = true;
    
    // ✅ 正确：当前方法"接力"处理
    public void correctMethod() {
        while (condition) {
            try {
                Thread.sleep(800);
                doWork();
            } catch (InterruptedException e) {
                // ✅ 正确"接力"处理
                // 1. 恢复中断状态
                Thread.currentThread().interrupt();
                
                // 2. 退出循环（停止继续sleep）
                break;
                
                // 3. 可选：清理资源
                // cleanup();
            }
        }
    }
    
    private void doWork() {
        System.out.println("Working...");
    }
}
