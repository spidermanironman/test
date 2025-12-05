# 线程TIMED_WAITING状态监控

## 问题：线程等待多久会上报TimeWaiting？

### 答案

在Java中，线程**立即**进入`TIMED_WAITING`状态，而不是等待一段时间后才进入。当线程调用以下方法时，会立即进入`TIMED_WAITING`状态：

- `Thread.sleep(timeout)`
- `Object.wait(timeout)`
- `LockSupport.parkNanos(timeout)`
- `LockSupport.parkUntil(deadline)`
- `Thread.join(timeout)`

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
