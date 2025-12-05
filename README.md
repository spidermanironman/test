# 线程TIMED_WAITING状态监控

## 问题：线程等待多久会上报TimeWaiting？

### 答案

在Java中，线程**立即**进入`TIMED_WAITING`状态，而不是等待一段时间后才进入。当线程调用以下方法时，会立即进入`TIMED_WAITING`状态：

- `Thread.sleep(timeout)`
- `Object.wait(timeout)`
- `LockSupport.parkNanos(timeout)` - 详见下方说明
- `LockSupport.parkUntil(deadline)`
- `Thread.join(timeout)`

## LockSupport.parkNanos(timeout) 详解

### 作用
`LockSupport.parkNanos(timeout)` 用于让当前线程暂停（阻塞）指定的纳秒数。

### 关键特性
1. **参数**：`timeout` - 暂停的纳秒数（1秒 = 1,000,000,000 纳秒）
2. **状态**：调用后线程会立即进入 `TIMED_WAITING` 状态
3. **唤醒**：
   - 时间到期后自动唤醒
   - 可以被其他线程通过 `LockSupport.unpark(thread)` **提前唤醒**
4. **优势**：
   - 不需要 `synchronized` 锁
   - 可以被提前唤醒（与 `Thread.sleep()` 不同）
   - 更底层，性能更好

### 与其他方法的区别

| 方法 | 需要锁 | 可提前唤醒 | 使用场景 |
|------|--------|-----------|---------|
| `Thread.sleep()` | 否 | 否（只能中断） | 简单延迟 |
| `Object.wait()` | 是（synchronized） | 是（notify/notifyAll） | 条件等待 |
| `LockSupport.parkNanos()` | 否 | 是（unpark） | 底层并发控制 |

### 实际应用
- **自旋锁优化**：在自旋等待时短暂暂停，避免 CPU 空转
- **AQS（AbstractQueuedSynchronizer）**：Java 并发工具类的底层实现
- **自定义等待/通知机制**：实现更灵活的线程同步

### 示例代码
查看 `LockSupportExample.java` 了解详细用法和示例。

### 监控长时间TIMED_WAITING的线程

如果你想要监控并上报**长时间**处于`TIMED_WAITING`状态的线程，可以使用`ThreadTimeWaitingMonitor`类。

**关键参数：**
- `reportThresholdMs`: 线程在`TIMED_WAITING`状态持续多少毫秒后上报
- `checkIntervalMs`: 检查线程状态的间隔（毫秒）

**示例：**
```java
// 线程在TIMED_WAITING状态超过5秒后上报，每1秒检查一次
ThreadTimeWaitingMonitor monitor = new ThreadTimeWaitingMonitor(5000, 1000);
```

### 运行示例

```bash
javac ThreadTimeWaitingMonitor.java
java ThreadTimeWaitingMonitor
```
