# 调用栈详细分析

## 完整调用链（从下往上）

```
#37 __libc_init                    [系统初始化]
#36 main (app_process64)           [应用进程启动]
#35 AndroidRuntime::start          [Android运行时启动]
#34 CallStaticVoidMethod           [JNI调用]
#33 CallStaticVoidMethodV          [JNI调用]
#32 InvokeWithVarArgs              [ART方法调用]
#31 art_quick_invoke_static_stub   [ART快速调用]
#30 ZygoteInit.main                [Zygote初始化]
#29 RuntimeInit$MethodAndArgsCaller.run [运行时初始化]
#28 art_jni_trampoline             [JNI桥接]
#27 Method_invoke                  [方法调用]
#26 InvokeMethod                   [ART方法调用]
#25 art_quick_invoke_static_stub   [ART快速调用]
#24 ActivityThread.main            [主线程启动] ⭐ 主线程入口
#23 Looper.loop                    [消息循环] ⭐ 主线程消息循环
#22 Looper.loopOnce                [单次循环]
#21 Handler.dispatchMessage        [消息分发]
#20 ActivityThread$H.handleMessage [处理系统消息] ⭐ 处理窗口事务
#19 TransactionExecutor.execute    [执行事务]
#18 TransactionExecutor.executeTransactionItems [执行事务项]
#17 TransactionExecutor.executeNonLifecycleItem [执行非生命周期项]
#16 WindowStateInsetsControlChangeItem.execute [执行Insets变化] ⭐ 窗口Insets变化
#15 ViewRootImpl$W.insetsControlChanged [Insets控制变化回调]
#14 ViewRootImpl.onInsetsStateChanged [Insets状态变化处理]
#13 InsetsController.onStateChanged [Insets控制器状态变化]
#12 InsetsSourceConsumer.applyLocalVisibilityOverride [应用可见性覆盖] ⚠️ 问题触发点
#11 art_jni_trampoline             [JNI桥接]
#10 android_util_Log_println_native [日志JNI调用] ⚠️ 开始日志操作
#09 __android_log_buf_write        [写入日志缓冲区]
#08 SetLogger::$_0::__invoke       [日志记录器调用]
#07 LogdLoggerLocked::operator()   [日志记录器加锁] 🔴 尝试获取锁
#06 std::mutex::lock()             [互斥锁加锁] 🔴 锁竞争
#05 MutexLockWithTimeout           [互斥锁超时等待] 🔴 等待锁
#04 ScopedTrace::ScopedTrace       [跟踪作用域]
#03 trace_begin_internal           [开始跟踪]
#02 should_trace                   [检查是否跟踪]
#01 __futex_wait_ex                [futex等待] 🔴 系统调用阻塞
#00 syscall                        [系统调用] 🔴 最终阻塞点
```

## 关键节点说明

### ⭐ 正常流程节点
- **ActivityThread.main**: 应用主线程入口
- **Looper.loop**: 主线程消息循环，正常处理消息
- **ActivityThread$H.handleMessage**: 处理系统消息，包括窗口事务
- **WindowStateInsetsControlChangeItem.execute**: 系统框架处理窗口Insets变化

### ⚠️ 问题触发节点
- **InsetsSourceConsumer.applyLocalVisibilityOverride**: 
  - 这是应用或系统代码中处理窗口Insets可见性的方法
  - 在此方法中调用了日志输出，触发了锁竞争

### 🔴 阻塞节点
- **LogdLoggerLocked::operator()**: 日志记录器尝试获取互斥锁
- **std::mutex::lock()**: C++标准库互斥锁加锁操作
- **MutexLockWithTimeout**: Android bionic库的互斥锁超时等待
- **__futex_wait_ex**: Linux futex机制，线程进入等待状态
- **syscall**: 系统调用，线程被挂起，等待锁释放

## 问题分析

### 阻塞原因
1. **锁持有者未知**: 堆栈只显示了等待锁的线程，没有显示持有锁的线程
2. **锁竞争**: 多个线程（包括主线程）同时尝试获取日志系统的互斥锁
3. **长时间持有**: 持有锁的线程可能正在执行耗时操作

### 为什么主线程会阻塞？
- 主线程在处理窗口Insets变化时，需要输出日志
- 日志系统使用互斥锁保护，同一时间只允许一个线程写入
- 如果其他线程正在写入日志（或持有锁），主线程必须等待
- 如果锁持有时间过长，主线程就会长时间阻塞

### 为什么会导致游戏卡死？
- 主线程是UI线程，负责所有界面更新和用户交互
- 主线程阻塞 = UI完全冻结
- 用户无法进行任何操作
- 如果阻塞超过5秒，系统会弹出ANR对话框

## 解决方案优先级

### P0 - 立即修复（解决卡死）
1. **移除问题路径中的日志调用**
   - 在 `applyLocalVisibilityOverride` 及其调用链中移除日志
   - 这是最快的解决方案

### P1 - 短期优化（防止再次发生）
2. **减少日志输出频率**
   - 使用日志级别控制
   - 生产环境禁用DEBUG/VERBOSE日志
   - 使用采样机制

### P2 - 长期优化（架构改进）
3. **异步日志处理**
   - 使用日志队列
   - 后台线程处理日志写入
   - 避免在主线程同步写入日志

## 诊断下一步

要完全理解问题，需要：

1. **找出持有锁的线程**
   - 获取完整的线程dump
   - 查看systrace中所有线程的状态
   - 找出哪个线程持有 `LogdLoggerLocked` 的互斥锁

2. **分析日志输出模式**
   - 检查logcat输出频率
   - 找出哪些代码路径频繁输出日志
   - 检查是否有日志风暴

3. **检查代码实现**
   - 查看 `applyLocalVisibilityOverride` 的实现
   - 检查是否有自定义日志实现
   - 分析日志调用的上下文
