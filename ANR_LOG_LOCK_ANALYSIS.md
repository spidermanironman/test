# ANR 日志锁分析指南

## 问题描述
主线程（`sysTid=19671`）在等待日志锁（log lock），需要确定是哪个线程持有该锁。

## 主线程阻塞状态

根据之前的分析，主线程的阻塞堆栈如下：

```
sysTid=19671 (主线程)
  - NonPI::MutexLockWithTimeout (libc.so)
  - std::__1::mutex::lock() (libc++.so)
  - art::InitLogging::LogdLoggerLocked::operator() (libartbase.so)
  - android::base::SetLogger (libbase.so)
  - __android_log_buf_write (liblog.so)
  - android::android_util_Log_println_native (libandroid_runtime.so)
  - android.view.InsetsSourceConsumer.applyLocalVisibilityOverride
  - android.view.InsetsController.onStateChanged
  - android.view.ViewRootImpl.onInsetsStateChanged
  - android.app.ActivityThread$H.handleMessage
```

## 分析方法

### 1. 识别持有锁的线程

要找到持有日志锁的线程，需要在 ANR dump 中查找：

**方法 A：查找正在执行日志操作的线程**
- 搜索所有线程堆栈中包含以下函数的线程：
  - `__android_log_buf_write`
  - `android::base::SetLogger`
  - `art::InitLogging`
  - `std::__1::mutex::lock()` 或 `std::__1::mutex::try_lock()`

**方法 B：查找处于 mutex 持有状态的线程**
- 查找堆栈中包含 `pthread_mutex_lock` 但不在等待状态的线程
- 查找堆栈中显示正在执行日志写入操作的线程

**方法 C：分析 futex 状态**
- 日志锁底层使用 futex（Fast Userspace Mutex）
- 查找处于 `futex_wait` 状态的线程，这些是等待锁的线程
- 查找不在等待状态但可能在持有锁的线程

### 2. 常见持有日志锁的线程类型

1. **logd 守护进程相关线程**
   - 名称可能包含 "logd" 或 "logger"
   - 负责将日志写入系统日志缓冲区

2. **其他应用线程正在执行日志操作**
   - 查找堆栈中包含 `Log.d()`, `Log.e()`, `Log.i()` 等调用
   - 查找堆栈中包含 `__android_log_buf_write` 的线程

3. **系统服务线程**
   - Binder 线程（名称如 "Binder:xxx"）
   - 系统服务线程在执行日志操作时可能持有锁

### 3. 分析步骤

1. **提取所有线程信息**
   ```bash
   grep -A 50 "sysTid=" anr_dump.txt > all_threads.txt
   ```

2. **查找日志相关调用**
   ```bash
   grep -B 5 -A 20 "__android_log_buf_write\|android::base::SetLogger\|art::InitLogging" anr_dump.txt
   ```

3. **查找 mutex 相关状态**
   ```bash
   grep -B 5 -A 20 "mutex\|MutexLock\|futex" anr_dump.txt
   ```

4. **分析线程状态**
   - 查找不在 `futex_wait` 状态的线程
   - 查找堆栈显示正在执行操作的线程（而非等待状态）

### 4. 判断标准

持有日志锁的线程通常具有以下特征之一：

1. **堆栈显示正在执行日志操作**
   - 堆栈中包含 `__android_log_buf_write` 且不在等待状态
   - 堆栈显示正在调用日志相关函数

2. **线程状态不是等待状态**
   - 不在 `futex_wait`, `epoll_wait`, `nanosleep` 等等待状态
   - 线程状态为 "R" (Running) 或 "D" (Disk sleep) 但正在执行日志操作

3. **Binder 线程或系统线程**
   - 名称包含 "Binder", "logd", "logger"
   - 系统服务线程在执行日志操作

### 5. 注意事项

- **所有线程都在等待状态的情况**：如果所有其他线程也都在等待状态（`futex_wait`, `epoll_wait` 等），可能的原因：
  1. 持有锁的线程不在当前 dump 中（可能是内核线程或已退出）
  2. 锁被系统服务持有，该线程的堆栈未包含在 dump 中
  3. 存在死锁情况，多个线程相互等待

- **日志锁的特殊性**：Android 日志系统使用全局锁，任何线程执行日志操作都可能持有该锁

## 建议的排查方向

1. **检查 logd 相关线程**：查找名称包含 "logd" 或负责日志处理的线程
2. **检查频繁日志输出的线程**：查找堆栈中频繁出现日志调用的线程
3. **检查 Binder 线程**：Binder 线程在执行日志操作时可能持有锁
4. **检查系统服务线程**：系统服务在执行日志操作时可能持有锁

## 如果无法直接识别

如果无法从 dump 中直接识别持有锁的线程，建议：

1. **添加日志**：在应用代码中添加更详细的日志，记录线程信息
2. **使用 systrace**：使用 systrace 工具追踪 mutex 的获取和释放
3. **减少日志输出**：临时减少日志输出频率，观察 ANR 是否消失
4. **检查日志配置**：检查是否有日志配置导致锁竞争加剧
