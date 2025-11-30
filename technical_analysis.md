# 游戏卡死技术分析报告

## 堆栈跟踪详情

### 线程信息
- **线程ID**: sysTid=19671
- **进程**: m.tencent.KiHan (腾讯游戏)
- **线程类型**: 主线程 (Main Thread / UI Thread)

### 阻塞位置

```
阻塞点: __futex_wait_ex() - 系统级互斥锁等待
├─ 调用位置: libc.so
├─ 等待对象: pthread_mutex_internal_t (日志系统互斥锁)
└─ 等待原因: MutexLockWithTimeout() 超时等待
```

### 调用链分析

#### 1. Android 框架层 (Framework)
```
#12-#15: ViewRootImpl 和 InsetsController
- WindowStateInsetsControlChangeItem.execute()
- ViewRootImpl$W.insetsControlChanged()
- ViewRootImpl.onInsetsStateChanged()
- InsetsController.onStateChanged()
- InsetsSourceConsumer.applyLocalVisibilityOverride()
```
**说明**: 系统通知应用窗口插入（状态栏、导航栏、键盘等）状态发生变化，需要更新 UI。

#### 2. 日志调用层 (Logging)
```
#07-#10: 日志系统调用
- LogdLoggerLocked::operator()
- android::base::SetLogger
- __android_log_buf_write
- android_util_Log_println_native
```
**说明**: 在处理插入状态变化时，代码尝试记录日志。

#### 3. 互斥锁层 (Mutex)
```
#05-#06: 互斥锁获取
- NonPI::MutexLockWithTimeout()
- std::__1::mutex::lock()
```
**说明**: 日志系统使用互斥锁保护共享资源，当前线程无法获取锁。

#### 4. 系统调用层 (System Call)
```
#00-#02: 系统级等待
- syscall()
- __futex_wait_ex()
- should_trace()
```
**说明**: 通过 futex（快速用户空间互斥锁）进入内核等待。

## 问题诊断

### 问题类型
**主线程阻塞 (Main Thread Blocking)**

### 阻塞原因分类

#### 可能性 1: 死锁 (Deadlock) - 高概率
```
线程A (主线程):
  持有: UI 资源锁
  等待: 日志系统互斥锁

线程B (后台线程):
  持有: 日志系统互斥锁
  等待: UI 资源锁 或 主线程持有的其他资源
```

#### 可能性 2: 日志锁长时间占用 - 高概率
```
后台线程:
  获取日志锁
  执行耗时操作（文件 I/O、网络、数据库等）
  长时间不释放锁

主线程:
  频繁尝试获取日志锁
  全部被阻塞
```

#### 可能性 3: 日志系统内部问题 - 低概率
```
日志守护进程 (logd) 响应慢
日志缓冲区满
系统资源不足
```

## Systrace 分析指南

### 需要检查的关键点

#### 1. 主线程状态
在 systrace 中查找：
- **线程名称**: `main` 或 `KiHan:main`
- **状态**: `R` (Running), `S` (Sleeping), `D` (Uninterruptible Sleep)
- **阻塞时长**: 如果长时间处于 `D` 状态，说明被阻塞

#### 2. 互斥锁事件
查找以下事件：
```
- futex_wait
- futex_wake
- mutex_lock
- mutex_unlock
```

关键信息：
- 哪个线程持有日志锁？
- 持有锁的时长？
- 有多少线程在等待这个锁？

#### 3. 日志相关线程
查找以下线程：
```
- logd (日志守护进程)
- logcat
- 应用中的日志线程
```

检查这些线程的活动：
- 是否在执行耗时操作？
- 是否长时间持有锁？

#### 4. Insets 相关事件
查找以下事件：
```
- insets_control_changed
- onInsetsStateChanged
- applyLocalVisibilityOverride
```

统计：
- 这些事件的调用频率
- 每次调用的耗时
- 是否与日志调用重叠

### Systrace 分析步骤

1. **打开 systrace HTML 文件**
   ```bash
   # 如果 systrace 文件是 HTML 格式
   chrome://tracing
   # 然后加载 HTML 文件
   ```

2. **定位问题时间点**
   - 找到主线程开始阻塞的时间点
   - 标记该时间点前后 1-2 秒的时间窗口

3. **查找持有锁的线程**
   - 在问题时间点，搜索 `futex` 或 `mutex` 事件
   - 找到持有锁的线程（状态为 `locked` 或 `held`）
   - 查看该线程在持有锁期间做了什么

4. **分析锁竞争**
   - 统计等待日志锁的线程数量
   - 查看等待时间分布
   - 找出等待时间最长的线程

5. **检查相关系统调用**
   - 查找 `syscall` 事件
   - 查看是否有大量的 `futex` 系统调用
   - 检查系统调用耗时

## 代码修复建议

### 1. 移除高频路径中的日志

找到以下代码位置并移除日志调用：

```java
// 可能的代码位置
class InsetsSourceConsumer {
    void applyLocalVisibilityOverride(...) {
        // ❌ 移除或注释掉这些日志
        // Log.d(TAG, "applyLocalVisibilityOverride: " + ...);
        // Log.v(TAG, "Visibility override applied");
        
        // ✅ 保留核心逻辑
        // ... UI 更新代码 ...
    }
}
```

### 2. 使用条件日志

```java
// 只在开发环境启用日志
if (BuildConfig.DEBUG && Log.isLoggable(TAG, Log.DEBUG)) {
    Log.d(TAG, "applyLocalVisibilityOverride");
}
```

### 3. 异步日志记录

```java
// 使用 Handler 将日志移到后台线程
private final Handler mLogHandler = new Handler(
    new HandlerThread("LogThread").getLooper()
);

void logAsync(String message) {
    mLogHandler.post(() -> {
        Log.d(TAG, message);
    });
}
```

### 4. 减少日志频率

```java
// 使用采样日志
private int mLogCounter = 0;
private static final int LOG_SAMPLE_RATE = 100; // 每100次记录一次

void logSampled(String message) {
    if (++mLogCounter % LOG_SAMPLE_RATE == 0) {
        Log.d(TAG, message);
    }
}
```

## 验证和测试

### 1. 复现问题
- 触发窗口插入状态变化（旋转屏幕、显示/隐藏键盘等）
- 观察是否出现卡死

### 2. 验证修复
- 移除可疑日志调用后重新测试
- 使用 systrace 确认主线程不再阻塞

### 3. 性能监控
```java
// 添加性能监控
long startTime = SystemClock.elapsedRealtime();
// ... 代码执行 ...
long duration = SystemClock.elapsedRealtime() - startTime;
if (duration > 16) { // 超过一帧时间
    // 记录性能问题
}
```

## 预防措施

1. **代码审查规则**
   - 禁止在主线程 UI 更新路径中使用同步日志
   - 使用异步日志或移除生产环境日志

2. **性能测试**
   - 定期运行 systrace 分析
   - 监控主线程阻塞情况

3. **日志策略**
   - 生产环境关闭 DEBUG/VERBOSE 日志
   - 使用远程日志服务，避免本地日志竞争

## 总结

**问题**: 主线程在处理窗口插入状态变化时，因日志系统互斥锁竞争导致阻塞。

**根本原因**: 
1. 在高频 UI 更新路径中调用同步日志
2. 日志系统互斥锁被其他线程长时间占用
3. 可能存在死锁情况

**解决方案优先级**:
1. ⚠️ **立即**: 移除 `applyLocalVisibilityOverride()` 及相关路径中的日志调用
2. 🔧 **短期**: 检查并优化所有持有日志锁的线程
3. 📊 **长期**: 建立日志策略和性能监控机制
