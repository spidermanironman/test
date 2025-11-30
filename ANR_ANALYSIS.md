# 线程Sleep被Interrupt唤醒导致ANR的原因分析

## 问题描述
线程在sleeping 800ms后被Interrupt唤醒，连续几次发生导致ANR（Application Not Responding）。

## 根本原因分析

### 1. **Interrupt机制的工作原理**
当线程调用`Thread.sleep(800)`时，线程会进入TIMED_WAITING状态。如果在此期间线程被interrupt：
- `InterruptedException`会被抛出
- 线程的interrupt标志位会被清除（设置为false）
- 线程立即从sleep状态唤醒，继续执行后续代码

### 2. **导致ANR的核心问题**

#### 问题场景1：频繁唤醒导致CPU占用过高
```
线程A: sleep(800ms) → 被interrupt → 立即重新sleep(800ms) → 又被interrupt → ...
```
如果interrupt操作非常频繁（比如每100ms一次），会导致：
- 线程频繁从sleep状态唤醒
- 每次唤醒都会消耗CPU资源进行上下文切换
- 如果主线程或关键线程被频繁唤醒，可能导致UI线程阻塞

#### 问题场景2：未正确处理InterruptedException
```java
// 错误示例
while (condition) {
    try {
        Thread.sleep(800);
    } catch (InterruptedException e) {
        // 没有检查interrupt状态，继续循环
        // 导致线程无法正常退出
    }
}
```

#### 问题场景3：在关键路径上被interrupt
如果被interrupt的线程是：
- **主线程（UI线程）**：直接导致ANR
- **关键工作线程**：阻塞了主线程等待的操作，间接导致ANR

### 3. **连续几次发生的连锁反应**

```
时间线：
T0: 线程开始sleep(800ms)
T1: 被interrupt唤醒（比如100ms后）
T2: 重新sleep(800ms)
T3: 又被interrupt唤醒（比如100ms后）
T4: 再次sleep(800ms)
...
```

**累积效应：**
- 每次interrupt都会触发异常处理逻辑
- 如果异常处理中有日志、监控上报等操作，会消耗额外时间
- 多次累积后，可能导致线程响应时间超过ANR阈值（通常5秒）

## 具体原因分类

### 原因1：竞态条件（Race Condition）
```java
// 线程A
Thread.sleep(800);

// 线程B（频繁调用）
threadA.interrupt();
```
如果线程B的interrupt调用频率高于800ms，线程A永远无法完成完整的sleep周期。

### 原因2：错误的循环逻辑
```java
while (!isStopped) {
    try {
        Thread.sleep(800);
        doWork(); // 如果这里耗时，可能导致ANR
    } catch (InterruptedException e) {
        // 没有退出循环，继续执行
    }
}
```

### 原因3：主线程被interrupt
如果主线程在sleep时被interrupt，且后续有耗时操作：
```java
// 主线程
try {
    Thread.sleep(800);
} catch (InterruptedException e) {
    // 如果这里执行了耗时操作，直接导致ANR
    heavyOperation(); // 超过5秒 → ANR
}
```

## 解决方案

### 方案1：正确处理InterruptedException
```java
while (!Thread.currentThread().isInterrupted()) {
    try {
        Thread.sleep(800);
        doWork();
    } catch (InterruptedException e) {
        // 恢复interrupt状态
        Thread.currentThread().interrupt();
        // 退出循环
        break;
    }
}
```

### 方案2：使用标志位控制
```java
private volatile boolean shouldStop = false;

while (!shouldStop) {
    try {
        Thread.sleep(800);
        doWork();
    } catch (InterruptedException e) {
        shouldStop = true;
        Thread.currentThread().interrupt();
    }
}
```

### 方案3：避免在主线程sleep
- 主线程不应该长时间sleep
- 使用Handler.postDelayed()或协程delay代替

### 方案4：限制interrupt频率
```java
// 在interrupt调用方添加节流
private long lastInterruptTime = 0;
private static final long MIN_INTERRUPT_INTERVAL = 1000; // 最小间隔1秒

public void interruptThread() {
    long now = System.currentTimeMillis();
    if (now - lastInterruptTime < MIN_INTERRUPT_INTERVAL) {
        return; // 忽略过于频繁的interrupt
    }
    lastInterruptTime = now;
    thread.interrupt();
}
```

### 方案5：使用更合适的同步机制
- 使用`Object.wait()` + `notify()`代替sleep
- 使用`CountDownLatch`、`Semaphore`等同步工具
- 使用`BlockingQueue`进行线程间通信

## 诊断方法

### 1. 查看ANR日志
```
/data/anr/traces.txt
```
查找：
- 线程状态：`"Thread-xxx" prio=5 tid=xx TIMED_WAITING`
- interrupt相关的堆栈

### 2. 添加日志监控
```java
try {
    Thread.sleep(800);
} catch (InterruptedException e) {
    Log.w(TAG, "Thread interrupted, count: " + interruptCount++);
    // 记录interrupt频率
    if (interruptCount > 5) {
        Log.e(TAG, "Too many interrupts!");
    }
    Thread.currentThread().interrupt();
}
```

### 3. 使用性能分析工具
- Android Studio Profiler
- Systrace
- 检查线程状态转换频率

## 总结

**导致ANR的核心原因：**
1. 线程被频繁interrupt，无法完成正常的sleep周期
2. InterruptedException处理不当，导致线程无法正常退出
3. 在关键线程（特别是主线程）上发生interrupt，且后续有耗时操作
4. 多次interrupt累积的异常处理开销超过ANR阈值

**关键要点：**
- 始终检查`Thread.currentThread().isInterrupted()`
- 捕获InterruptedException后要恢复interrupt状态
- 避免在主线程使用sleep
- 控制interrupt的调用频率
