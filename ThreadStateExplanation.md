# 线程 TIMED_WAITING 状态说明

## 核心概念

**线程不会"等待多久后"才进入 TIMED_WAITING 状态，而是在调用带超时参数的方法时，立即进入 TIMED_WAITING 状态。**

## 进入 TIMED_WAITING 状态的方法

以下方法调用时会**立即**让线程进入 `TIMED_WAITING` 状态：

1. **`Thread.sleep(timeout)`** - 线程休眠指定时间
2. **`Object.wait(timeout)`** - 在对象上等待，带超时
3. **`Thread.join(timeout)`** - 等待另一个线程完成，带超时
4. **`LockSupport.parkNanos(timeout)`** - 暂停线程，带纳秒超时
5. **`LockSupport.parkUntil(deadline)`** - 暂停线程直到指定时间

## 状态持续时间

线程会保持在 `TIMED_WAITING` 状态，直到：
- 超时时间到期
- 线程被中断（`interrupt()`）
- 其他唤醒条件满足（如 `notify()` 对于 `wait()`）

## 示例

```java
Thread thread = new Thread(() -> {
    try {
        Thread.sleep(5000); // 立即进入 TIMED_WAITING 状态
    } catch (InterruptedException e) {
        // 处理中断
    }
});

thread.start();
Thread.sleep(100); // 等待线程启动
System.out.println(thread.getState()); // 输出: TIMED_WAITING
```

## 监控工具中的显示

在以下工具中，线程会显示为 `TIMED_WAITING` 状态：
- **jstack** - Java 线程转储工具
- **jvisualvm** - Java 可视化监控工具
- **jconsole** - Java 监控和管理控制台
- **Thread.getState()** - Java API

这些工具会**立即**显示线程的 `TIMED_WAITING` 状态，不需要等待任何时间。

## 总结

- ✅ 线程在调用带超时的方法时**立即**进入 `TIMED_WAITING`
- ❌ 线程**不会**等待一段时间后才进入 `TIMED_WAITING`
- ⏱️ 线程会保持在 `TIMED_WAITING` 状态直到超时或中断
