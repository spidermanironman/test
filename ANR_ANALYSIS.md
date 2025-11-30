# 线程Sleep被Interrupt导致ANR的原因分析

## 问题描述
线程sleep 800ms后被Interrupt唤醒，连续几次发生导致ANR。

## ANR发生的根本原因

### 1. **主线程被阻塞**
如果sleep操作发生在**主线程（UI线程）**上，这是最直接的原因：
- Android系统要求主线程在5秒内响应（某些操作是10秒）
- 如果主线程sleep 800ms，被interrupt后立即再次sleep，连续几次就会累积超过ANR阈值
- 例如：800ms × 7次 = 5.6秒 > 5秒阈值 → ANR

### 2. **Interrupt处理不当导致循环阻塞**
```java
// 错误示例：在主线程上
while (someCondition) {
    try {
        Thread.sleep(800);  // 主线程阻塞800ms
    } catch (InterruptedException e) {
        // 没有恢复中断状态，继续循环
        // 如果条件仍然满足，会再次sleep
    }
}
```

### 3. **中断状态未清除**
当线程被interrupt后：
- `InterruptedException`被抛出
- 但线程的中断状态会被**清除**
- 如果代码没有正确处理，可能会：
  - 忽略中断，继续执行
  - 没有检查中断状态，导致无法及时退出循环
  - 在循环中重复sleep，累积阻塞时间

### 4. **资源竞争和死锁**
连续interrupt可能导致：
- 线程状态混乱
- 锁竞争加剧
- 其他线程等待该线程释放资源，形成连锁阻塞

## 典型场景

### 场景1：主线程上的循环Sleep
```java
// 危险代码：在主线程执行
public void processData() {
    while (!isComplete) {
        try {
            Thread.sleep(800);  // 主线程阻塞！
        } catch (InterruptedException e) {
            // 没有退出循环，继续sleep
        }
    }
}
```

### 场景2：中断后未恢复中断标志
```java
// 问题代码
public void run() {
    while (running) {
        try {
            Thread.sleep(800);
            doWork();
        } catch (InterruptedException e) {
            // 中断标志被清除，但循环继续
            // 如果running仍为true，会再次sleep
        }
    }
}
```

## 解决方案

### 1. **避免在主线程上Sleep**
```java
// 正确：使用Handler或协程延迟
Handler handler = new Handler(Looper.getMainLooper());
handler.postDelayed(() -> {
    // 执行操作
}, 800);
```

### 2. **正确处理InterruptedException**
```java
// 正确：恢复中断状态并退出
public void run() {
    while (running) {
        try {
            Thread.sleep(800);
            doWork();
        } catch (InterruptedException e) {
            // 恢复中断状态
            Thread.currentThread().interrupt();
            // 退出循环
            break;
        }
    }
}
```

### 3. **检查中断状态**
```java
// 正确：定期检查中断状态
public void run() {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Thread.sleep(800);
            doWork();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            break;
        }
    }
}
```

### 4. **使用更合适的并发机制**
```java
// 使用CountDownLatch、Semaphore等替代sleep
// 或使用ScheduledExecutorService
ScheduledExecutorService executor = Executors.newScheduledThreadPool(1);
executor.schedule(() -> {
    // 执行操作
}, 800, TimeUnit.MILLISECONDS);
```

## 总结

**导致ANR的核心原因：**
1. **主线程被阻塞**：sleep发生在UI线程
2. **累积阻塞时间**：连续多次sleep超过5秒阈值
3. **中断处理不当**：没有及时退出循环，导致重复阻塞
4. **资源竞争**：多个线程相互等待，形成死锁

**关键点：**
- 永远不要在主线程上使用Thread.sleep()
- 正确处理InterruptedException，恢复中断状态
- 使用Android提供的异步机制（Handler、Coroutines、RxJava等）
- 定期检查中断状态，及时退出长时间运行的循环
