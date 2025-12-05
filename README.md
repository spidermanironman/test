# 广播线程状态检查工具

## 功能说明

这个工具用于检查和监控所有处理广播的线程状态，确保它们都处于正常状态。

## 核心功能

### 1. 线程状态监控
- **注册线程**: 当广播接收器开始处理广播时，自动注册处理线程
- **状态跟踪**: 实时跟踪每个线程的状态（正常、阻塞、等待、已终止等）
- **状态更新**: 在广播处理过程中更新线程状态

### 2. 状态检查方法

#### `checkAllBroadcastThreadsNormal()`
检查所有广播处理线程状态是否均正常。

**返回值**:
- `true`: 所有线程状态正常
- `false`: 存在异常线程

**使用示例**:
```java
boolean allNormal = BroadcastThreadStatusChecker.checkAllBroadcastThreadsNormal();
if (allNormal) {
    Log.i("Status", "✓ 所有广播处理线程状态均正常");
} else {
    Log.e("Status", "✗ 发现异常线程");
}
```

#### `getThreadStatusReport()`
获取详细的线程状态报告，包括：
- 总线程数
- 每个线程的详细信息（名称、ID、状态、关联的广播）
- 正常线程数量统计

**使用示例**:
```java
String report = BroadcastThreadStatusChecker.getThreadStatusReport();
Log.d("Report", report);
```

## 线程状态类型

- **NORMAL**: 线程正常运行（NEW 或 RUNNABLE 状态）
- **BLOCKED**: 线程被阻塞
- **WAITING**: 线程在等待
- **TIMED_WAITING**: 线程在定时等待
- **TERMINATED**: 线程已终止

## 使用方法

### 1. 在广播接收器中注册线程

```java
public class MyBroadcastReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String threadName = Thread.currentThread().getName();
        String action = intent.getAction();
        
        // 注册当前处理线程
        BroadcastThreadStatusChecker.registerBroadcastThread(threadName, action);
        
        // 执行广播处理...
    }
}
```

### 2. 定期检查线程状态

```java
// 在需要检查的地方调用
boolean allNormal = BroadcastThreadStatusChecker.checkAllBroadcastThreadsNormal();
```

### 3. 获取详细报告

```java
// 获取完整的状态报告
String report = BroadcastThreadStatusChecker.getThreadStatusReport();
System.out.println(report);
```

### 4. 清理已终止的线程

```java
// 定期清理已终止的线程记录
BroadcastThreadStatusChecker.cleanupTerminatedThreads();
```

## 判断"所有线程状态均正常"的标准

1. **线程存在**: 所有已注册的线程仍然存在
2. **状态正常**: 所有线程的状态为 `NORMAL`（即 Java 线程状态为 NEW 或 RUNNABLE）
3. **无阻塞**: 没有线程处于 BLOCKED、WAITING 或 TIMED_WAITING 状态
4. **未终止**: 没有线程处于 TERMINATED 状态

## 日志输出示例

### 正常情况
```
D/BroadcastThreadChecker: 注册广播线程: main, 状态: NORMAL
I/BroadcastThreadChecker: ✓ 所有广播处理线程状态均正常
```

### 异常情况
```
W/BroadcastThreadChecker: 线程状态异常: BroadcastThread-1, 状态: BLOCKED
E/BroadcastThreadChecker: ✗ 发现 1 个异常线程:
E/BroadcastThreadChecker:   - BroadcastThread-1 (ID: 12345, 状态: BLOCKED, 广播: android.intent.action.BOOT_COMPLETED)
```

## 注意事项

1. 线程状态检查是实时的，每次调用都会重新检查当前状态
2. 已终止的线程会被标记为异常，需要定期调用 `cleanupTerminatedThreads()` 清理
3. 在多线程环境下，状态检查是线程安全的（使用 ConcurrentHashMap）
4. 建议在广播处理的开始和结束都进行状态检查
