# InterruptedException处理责任链（接力机制）

## 问题：中断异常应该由谁来处理？

当线程在sleep时被interrupt，`InterruptedException`应该由**调用链中的哪一层**来处理？

## 核心原则

### 1. **谁调用可中断方法，谁负责处理**

```
调用链：A → B → C → Thread.sleep()
         ↑    ↑    ↑
         |    |    └─ 抛出InterruptedException
         |    └─ 必须处理或传播
         └─ 最终处理者
```

### 2. **责任分层**

#### 层次1：底层方法（抛出异常）
```java
// 底层：抛出InterruptedException
public void lowLevelMethod() throws InterruptedException {
    Thread.sleep(800);  // 可能抛出InterruptedException
}
```
**责任**：声明 `throws InterruptedException`，让调用者知道可能被中断

#### 层次2：中层方法（传播或处理）
```java
// 方案A：继续传播（如果无法处理）
public void middleLevelMethod() throws InterruptedException {
    lowLevelMethod();  // 传播异常
}

// 方案B：转换为运行时异常（如果不应该中断）
public void middleLevelMethod() {
    try {
        lowLevelMethod();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();  // 恢复中断状态
        throw new RuntimeException("Unexpected interruption", e);
    }
}

// 方案C：正确处理（如果可以处理）
public void middleLevelMethod() {
    try {
        lowLevelMethod();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // 清理资源、退出循环等
        return;  // 或 break
    }
}
```

#### 层次3：顶层方法（最终处理）
```java
// 顶层：必须处理，不能忽略
public void topLevelMethod() {
    try {
        middleLevelMethod();
    } catch (InterruptedException e) {
        // ✅ 必须恢复中断状态
        Thread.currentThread().interrupt();
        // ✅ 执行清理工作
        cleanup();
        // ✅ 记录日志
        logger.warn("Thread interrupted", e);
    }
}
```

## 具体场景分析

### 场景1：Worker线程中的sleep

```java
// ✅ 正确：Worker线程自己处理中断
public class WorkerThread extends Thread {
    @Override
    public void run() {
        while (!isInterrupted()) {
            try {
                Thread.sleep(800);
                doWork();
            } catch (InterruptedException e) {
                // ✅ Worker线程自己"接力"处理
                Thread.currentThread().interrupt();
                break;  // 退出循环
            }
        }
    }
}
```

**责任归属**：**Worker线程自己**，因为它在自己的run()方法中调用sleep

### 场景2：业务方法调用sleep

```java
// 业务层方法
public class BusinessService {
    // ❌ 错误：业务方法不应该直接sleep
    public void processData() {
        try {
            Thread.sleep(800);  // 业务层不应该直接sleep
        } catch (InterruptedException e) {
            // 业务层不知道如何处理中断
        }
    }
}

// ✅ 正确：业务层委托给工具类
public class BusinessService {
    private DelayUtil delayUtil;
    
    public void processData() {
        delayUtil.delay(800);  // 委托给工具类
    }
}

// 工具类负责处理中断
public class DelayUtil {
    public void delay(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            // ✅ 工具类"接力"处理
            Thread.currentThread().interrupt();
            throw new RuntimeException("Delay interrupted", e);
        }
    }
}
```

**责任归属**：
- 如果业务层直接调用sleep → **业务层负责**
- 如果委托给工具类 → **工具类负责**

### 场景3：框架/库方法

```java
// 框架方法：应该传播异常
public class FrameworkUtil {
    // ✅ 正确：框架层传播异常，让调用者决定
    public void frameworkMethod() throws InterruptedException {
        Thread.sleep(800);
        // 框架不知道业务逻辑，应该让调用者处理
    }
}

// 应用层：必须处理
public class Application {
    public void appMethod() {
        try {
            frameworkMethod();
        } catch (InterruptedException e) {
            // ✅ 应用层"接力"处理
            Thread.currentThread().interrupt();
            handleInterruption();
        }
    }
}
```

**责任归属**：
- **框架层**：传播异常（throws）
- **应用层**：最终处理

### 场景4：Runnable/Callable中的sleep

```java
// ExecutorService提交的任务
ExecutorService executor = Executors.newFixedThreadPool(1);

Future<?> future = executor.submit(() -> {
    // ✅ 任务自己"接力"处理
    try {
        Thread.sleep(800);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // 任务被中断，退出
        return;
    }
    doWork();
});

// 如果需要取消任务
future.cancel(true);  // interrupt = true
```

**责任归属**：**Runnable/Callable任务本身**，因为它在自己的执行上下文中

## 关键规则总结

### ✅ 应该"接力"处理的情况

1. **直接调用可中断方法的代码**
   ```java
   try {
       Thread.sleep(800);  // 你调用的，你处理
   } catch (InterruptedException e) {
       // 必须处理
   }
   ```

2. **无法继续传播的顶层方法**
   ```java
   public void mainMethod() {  // 不能throws
       try {
           subMethod();  // throws InterruptedException
       } catch (InterruptedException e) {
           // 必须在这里处理
       }
   }
   ```

3. **线程的run()方法**
   ```java
   public void run() {
       try {
           Thread.sleep(800);
       } catch (InterruptedException e) {
           // run()方法必须处理，不能throws
       }
   }
   ```

### ❌ 不应该"接力"处理的情况

1. **可以继续传播的方法**
   ```java
   // ✅ 正确：继续传播
   public void method() throws InterruptedException {
       Thread.sleep(800);  // 让调用者处理
   }
   ```

2. **不知道如何处理的中层方法**
   ```java
   // ✅ 正确：传播给知道如何处理的层
   public void middleMethod() throws InterruptedException {
       lowLevelMethod();  // 传播异常
   }
   ```

## 针对你的ANR问题

### 问题代码
```java
// 连续几次sleep被interrupt
while (condition) {
    try {
        Thread.sleep(800);
    } catch (InterruptedException e) {
        // ❌ 问题：没有"接力"处理
        // 应该：恢复中断状态 + 退出循环
    }
}
```

### 正确的"接力"处理
```java
// ✅ 正确：当前方法"接力"处理
while (condition) {
    try {
        Thread.sleep(800);
    } catch (InterruptedException e) {
        // ✅ 1. 恢复中断状态（让其他代码知道被中断了）
        Thread.currentThread().interrupt();
        
        // ✅ 2. 退出循环（停止继续sleep）
        break;  // 或 return
        
        // ✅ 3. 清理资源（如果需要）
        cleanup();
    }
}
```

## 总结

**"接力"的责任归属：**

1. **直接调用sleep的代码** → 必须处理或传播
2. **无法传播的顶层方法** → 必须处理
3. **线程的run()方法** → 必须处理
4. **可以传播的中层方法** → 可以传播给调用者

**核心原则：**
- 谁调用，谁负责（或传播）
- 不能传播的地方，必须处理
- 处理时：恢复中断状态 + 退出/清理
