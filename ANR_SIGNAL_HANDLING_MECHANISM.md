# ANR信号处理机制详解

## 概述
本文档详细解释Android系统中，从ANR检测到信号发送、应用处理、以及信号恢复的完整流程。

---

## 一、ANR触发到appNotResponding的流程

### 1.1 ANR检测触发
ANR可能由以下几种场景触发：
- **Input事件超时**：5秒内未处理完输入事件
- **BroadcastReceiver超时**：前台10秒，后台60秒
- **Service超时**：前台20秒，后台200秒
- **ContentProvider超时**：10秒

### 1.2 进入ProcessErrorStateRecord.appNotResponding()

当ANR发生时，系统会调用 `ProcessErrorStateRecord.appNotResponding()` 方法：

```java
// ProcessErrorStateRecord.java
void appNotResponding(String activityShortComponentName, 
                      ApplicationInfo aInfo,
                      String parentShortComponentName,
                      WindowProcessController parentProcess,
                      boolean aboveSystem, 
                      String annotation,
                      boolean onlyDumpSelf) {
    
    // 1. 设置ANR状态
    synchronized (mService) {
        mNotResponding = true;
        mNotRespondingReport = null;
    }
    
    // 2. 记录ANR时间
    long anrTime = SystemClock.uptimeMillis();
    
    // 3. 收集ANR相关信息
    // - CPU使用情况
    // - 内存信息
    // - 线程堆栈信息
    
    // 4. 准备发送SIGNAL_QUIT (Signal 3) 收集traces
    ...
}
```

---

## 二、发送Signal 3 (SIGQUIT)的完整流程

### 2.1 准备发送信号

```java
// ProcessErrorStateRecord.java
void appNotResponding(...) {
    // 创建一个ArrayList存储需要dump traces的进程
    ArrayList<Integer> firstPids = new ArrayList<>(5);
    SparseArray<Boolean> lastPids = new SparseArray<>(20);
    
    // 添加当前ANR进程
    firstPids.add(mApp.getPid());
    
    // 添加系统关键进程
    // - system_server
    // - persistent进程
    
    // 发送信号前，先设置一个临时的信号处理器
    // 这是关键步骤！
    prepareSigQuitHandling();
    
    // 调用dumpStackTraces收集堆栈
    File tracesFile = ActivityManagerService.dumpStackTraces(
        firstPids,
        processCpuTracker,
        lastPids,
        nativePids,
        tracesFileException,
        offsets,
        annotation
    );
}
```

### 2.2 dumpStackTraces核心实现

```java
// ActivityManagerService.java
public static File dumpStackTraces(ArrayList<Integer> firstPids,
                                   ProcessCpuTracker processCpuTracker,
                                   SparseArray<Boolean> lastPids,
                                   ArrayList<Integer> nativePids,
                                   StringWriter logExceptionCreatingFile,
                                   long[] firstPidOffsets,
                                   String subject) {
    
    // 1. 准备traces文件
    File tracesDir = new File("/data/anr");
    File tracesFile = new File(tracesDir, "traces.txt");
    
    try {
        // 2. 对每个firstPids中的进程发送SIGQUIT
        for (int i = 0; i < firstPids.size(); i++) {
            int pid = firstPids.get(i);
            
            // 记录文件偏移量
            firstPidOffsets[i] = tracesFile.length();
            
            // 关键：发送Signal 3
            // 这里会调用Process.sendSignal()
            Process.sendSignal(pid, Process.SIGNAL_QUIT);
            
            // 等待该进程完成traces写入
            // 超时时间：5秒
            long timeout = 5000;
            long start = SystemClock.uptimeMillis();
            
            while (true) {
                // 检查文件大小是否增长（表示traces已写入）
                long newSize = tracesFile.length();
                if (newSize > firstPidOffsets[i]) {
                    break; // traces已写入
                }
                
                if (SystemClock.uptimeMillis() - start > timeout) {
                    // 超时，该进程可能无响应
                    Slog.w(TAG, "Timeout waiting for process " + pid);
                    break;
                }
                
                // 短暂休眠后重试
                Thread.sleep(100);
            }
        }
        
        // 3. 继续处理lastPids和nativePids...
        
    } catch (Exception e) {
        // 处理异常
    }
    
    return tracesFile;
}
```

### 2.3 Process.sendSignal的底层实现

```java
// Process.java
public static final void sendSignal(int pid, int signal) {
    sendSignalQuiet(pid, signal);
}

private static native void sendSignalQuiet(int pid, int signal);
```

Native层实现（android_util_Process.cpp）：

```cpp
// android_util_Process.cpp
static void android_os_Process_sendSignalQuiet(JNIEnv* env, jobject clazz, 
                                                jint pid, jint sig) {
    if (pid > 0) {
        // 调用Linux系统调用kill发送信号
        // SIGNAL_QUIT = 3 (SIGQUIT)
        kill(pid, sig);
    }
}
```

---

## 三、应用进程接收Signal 3的处理流程

### 3.1 信号处理器注册

Android应用在启动时（Zygote fork后），会注册信号处理器：

```cpp
// signal_catcher.cc (ART Runtime)
void SignalCatcher::SetupSignalHandling() {
    struct sigaction sig_action;
    memset(&sig_action, 0, sizeof(sig_action));
    
    // 设置信号处理函数
    sig_action.sa_sigaction = SignalCatcher::HandleSigQuit;
    sig_action.sa_flags = SA_SIGINFO;
    sigemptyset(&sig_action.sa_mask);
    
    // 注册SIGQUIT (Signal 3)处理器
    if (sigaction(SIGQUIT, &sig_action, nullptr) != 0) {
        PLOG(ERROR) << "Failed to register SIGQUIT handler";
    }
}
```

### 3.2 信号处理函数

当应用进程收到Signal 3时：

```cpp
// signal_catcher.cc
void SignalCatcher::HandleSigQuit(int signal_number, 
                                   siginfo_t* info, 
                                   void* context) {
    // 1. 标记信号已接收
    // 这是一个异步信号处理器，需要小心处理
    
    // 2. 唤醒SignalCatcher线程
    // 通过写入pipe通知SignalCatcher线程
    char buf = 'q'; // 'q' for quit signal
    write(signal_catcher_pipe_[1], &buf, 1);
    
    // 信号处理器应该尽快返回
}
```

### 3.3 SignalCatcher线程处理

SignalCatcher是应用中的一个守护线程，专门处理信号：

```cpp
// signal_catcher.cc
void* SignalCatcher::Run(void* arg) {
    SignalCatcher* signal_catcher = reinterpret_cast<SignalCatcher*>(arg);
    Runtime* runtime = Runtime::Current();
    
    // 设置线程名称
    pthread_setname_np(pthread_self(), "Signal Catcher");
    
    while (true) {
        // 阻塞等待信号通知
        char buf;
        ssize_t result = read(signal_catcher->signal_catcher_pipe_[0], &buf, 1);
        
        if (result == 1) {
            if (buf == 'q') {
                // 收到SIGQUIT信号
                signal_catcher->HandleSigQuit();
            }
        }
    }
    
    return nullptr;
}

void SignalCatcher::HandleSigQuit() {
    // 1. 打开traces文件
    int fd = open("/data/anr/traces.txt", 
                  O_WRONLY | O_CREAT | O_APPEND, 
                  0666);
    
    if (fd < 0) {
        PLOG(ERROR) << "Failed to open traces file";
        return;
    }
    
    // 2. 输出进程信息
    DumpProcessInfo(fd);
    
    // 3. 输出所有线程的堆栈
    // 这是最耗时的部分
    Runtime::Current()->GetThreadList()->DumpForSigQuit(fd);
    
    // 4. 输出其他运行时信息
    // - Heap信息
    // - GC统计
    // - JNI引用
    
    // 5. 关闭文件
    close(fd);
    
    // 6. 完成！
    // system_server会检测到文件大小增长，知道traces已写入
}
```

### 3.4 线程堆栈Dump实现

```cpp
// thread_list.cc
void ThreadList::DumpForSigQuit(std::ostream& os) {
    MutexLock mu(Thread::Current(), *Locks::thread_list_lock_);
    
    os << "DALVIK THREADS (" << list_.size() << "):\n";
    
    for (Thread* thread : list_) {
        // 输出每个线程的信息
        thread->DumpState(os);
        thread->DumpStack(os);
    }
}
```

---

## 四、守护线程的Signal恢复机制（10秒超时）

这是ANR处理中非常重要但容易被忽略的机制！

### 4.1 为什么需要信号恢复机制？

**问题背景**：
- 当发送Signal 3时，应用需要dump所有线程堆栈
- 如果应用已经严重卡死，可能永远无法完成traces dump
- 如果不恢复信号，应用会一直阻塞在信号处理中
- 可能导致system_server也被拖住

**解决方案**：
- 使用一个守护线程，在发送Signal 3后启动10秒定时器
- 如果10秒后traces仍未完成，强制恢复信号处理

### 4.2 信号恢复的实现原理

#### 方案一：使用临时信号处理器（较老的实现）

```cpp
// signal_catcher.cc (早期版本)
void SignalCatcher::SetupTemporarySignalHandler() {
    struct sigaction temp_action;
    memset(&temp_action, 0, sizeof(temp_action));
    
    // 设置临时处理器，带SA_RESETHAND标志
    // SA_RESETHAND：信号处理后自动恢复为默认处理
    temp_action.sa_sigaction = TemporarySignalHandler;
    temp_action.sa_flags = SA_SIGINFO | SA_RESETHAND;
    
    sigaction(SIGQUIT, &temp_action, &old_action_);
    
    // 启动恢复线程
    pthread_t recovery_thread;
    pthread_create(&recovery_thread, nullptr, 
                   SignalRecoveryThread, this);
}

void* SignalRecoveryThread(void* arg) {
    // 设置为守护线程
    pthread_detach(pthread_self());
    
    // 等待10秒
    sleep(10);
    
    // 恢复原始信号处理器
    SignalCatcher* catcher = static_cast<SignalCatcher*>(arg);
    sigaction(SIGQUIT, &catcher->old_action_, nullptr);
    
    return nullptr;
}
```

#### 方案二：使用alarm定时器（现代实现）

```cpp
// signal_catcher.cc (现代版本)
class SignalCatcher {
private:
    static void AlarmHandler(int sig) {
        // alarm触发，强制结束traces dump
        trace_dumping_ = false;
    }
    
    void HandleSigQuitWithTimeout() {
        // 1. 设置alarm信号处理器
        struct sigaction alarm_action;
        memset(&alarm_action, 0, sizeof(alarm_action));
        alarm_action.sa_handler = AlarmHandler;
        sigaction(SIGALRM, &alarm_action, nullptr);
        
        // 2. 设置10秒alarm
        alarm(10);
        
        // 3. 开始dump traces
        trace_dumping_ = true;
        int fd = open("/data/anr/traces.txt", 
                      O_WRONLY | O_CREAT | O_APPEND, 
                      0666);
        
        if (fd >= 0) {
            // Dump线程堆栈
            // 检查trace_dumping_标志，如果变为false则中断
            DumpStacksWithInterrupt(fd);
            close(fd);
        }
        
        // 4. 取消alarm
        alarm(0);
        trace_dumping_ = false;
    }
    
    void DumpStacksWithInterrupt(int fd) {
        ThreadList* thread_list = Runtime::Current()->GetThreadList();
        
        for (Thread* thread : thread_list->GetList()) {
            // 每dump一个线程前检查标志
            if (!trace_dumping_) {
                // 超时了，停止dump
                write(fd, "\n[TRUNCATED - timeout]\n", 24);
                break;
            }
            
            thread->DumpState(fd);
            thread->DumpStack(fd);
        }
    }
};
```

#### 方案三：使用watchdog线程（最新实现）

```cpp
// signal_catcher.cc (Android 12+)
class SignalCatcher {
private:
    class DumpWatchdog {
    public:
        DumpWatchdog(int timeout_seconds) 
            : timeout_seconds_(timeout_seconds),
              timed_out_(false) {
            // 创建watchdog线程
            pthread_create(&watchdog_thread_, nullptr, 
                          WatchdogThread, this);
        }
        
        ~DumpWatchdog() {
            // 通知watchdog线程退出
            completed_ = true;
            pthread_join(watchdog_thread_, nullptr);
        }
        
        bool HasTimedOut() const { 
            return timed_out_; 
        }
        
    private:
        static void* WatchdogThread(void* arg) {
            DumpWatchdog* watchdog = static_cast<DumpWatchdog*>(arg);
            
            // 等待超时时间
            for (int i = 0; i < watchdog->timeout_seconds_ * 10; i++) {
                if (watchdog->completed_) {
                    // dump已完成
                    return nullptr;
                }
                usleep(100000); // 100ms
            }
            
            // 超时！
            watchdog->timed_out_ = true;
            
            // 强制中断dump操作
            // 可以通过发送信号给主线程或设置标志位
            
            return nullptr;
        }
        
        int timeout_seconds_;
        std::atomic<bool> timed_out_;
        std::atomic<bool> completed_;
        pthread_t watchdog_thread_;
    };
    
public:
    void HandleSigQuit() {
        // 创建watchdog，10秒超时
        DumpWatchdog watchdog(10);
        
        int fd = open("/data/anr/traces.txt", 
                      O_WRONLY | O_CREAT | O_APPEND, 
                      0666);
        
        if (fd >= 0) {
            Runtime* runtime = Runtime::Current();
            ThreadList* thread_list = runtime->GetThreadList();
            
            // Dump线程信息
            for (Thread* thread : thread_list->GetList()) {
                if (watchdog.HasTimedOut()) {
                    // 超时了，停止dump
                    const char* msg = "\n[DUMP INTERRUPTED - 10s timeout]\n";
                    write(fd, msg, strlen(msg));
                    break;
                }
                
                thread->DumpState(fd);
                thread->DumpStack(fd);
            }
            
            close(fd);
        }
        
        // watchdog析构时会等待线程退出
    }
};
```

### 4.3 信号恢复的关键要点

**1. 超时时间设计**：
- 10秒是一个权衡的结果
- 太短：可能无法收集完整traces
- 太长：ANR处理时间过长，影响用户体验

**2. 线程安全**：
- 信号处理器在异步上下文中执行
- 需要使用atomic变量或其他同步机制
- 避免死锁

**3. 优雅降级**：
- 即使超时，也要保存已收集的部分traces
- 在文件中标记超时信息
- 确保文件描述符被正确关闭

**4. 与system_server的协调**：
```java
// ActivityManagerService.java
// system_server端的等待逻辑
long timeout = 5000; // 5秒超时
long start = SystemClock.uptimeMillis();

while (SystemClock.uptimeMillis() - start < timeout) {
    long newSize = tracesFile.length();
    if (newSize > lastSize) {
        // 文件在增长，说明应用还在写入
        lastSize = newSize;
        lastGrowthTime = SystemClock.uptimeMillis();
    } else if (SystemClock.uptimeMillis() - lastGrowthTime > 1000) {
        // 1秒内文件没有增长，认为写入完成
        break;
    }
    
    Thread.sleep(100);
}
```

---

## 五、完整时序图

```
system_server                     应用进程                    Watchdog线程
     |                               |                              |
     | ANR detected                  |                              |
     |------------------------------>|                              |
     |                               |                              |
     | appNotResponding()            |                              |
     |------------------------------>|                              |
     |                               |                              |
     | dumpStackTraces()             |                              |
     |------------------------------>|                              |
     |                               |                              |
     | sendSignal(pid, SIGQUIT)      |                              |
     |------------------------------>| 接收Signal 3                 |
     |                               |----------------------------->|
     |                               |                              |
     |                               | 唤醒SignalCatcher线程        |
     |                               |----------------------------->|
     |                               |                              |
     |                               |                     创建Watchdog
     |                               |                              |
     |                               |                    启动10秒定时器
     |                               |                              |
     |                               |                     打开traces文件
     |                               |                              |
     |                               |                     Dump线程堆栈
     | 轮询traces文件大小            |                       (可能很慢)
     |<------------------------------|<-----------------------------|
     |                               |                              |
     | 文件大小增长?                 |                              |
     |------------------------------>|                              |
     |                               |                              |
     | YES - traces写入完成          |                     完成dump |
     |<------------------------------|<-----------------------------|
     |                               |                              |
     | 或者...                       |                              |
     |                               |                    10秒超时！|
     |                               |                              |
     |                               |                    设置超时标志
     |                               |                              |
     |                               |                    中断dump操作
     |                               |                              |
     |                               |                    写入超时标记
     |                               |                              |
     |                               |                    关闭文件  |
     |                               |                              |
     | 继续ANR处理                   |                              |
     | - 显示ANR对话框               |                              |
     | - 记录event log               |                              |
     | - 可能kill进程                |                              |
     |                               |                              |
```

---

## 六、关键代码路径总结

### 6.1 System Server端

```
ProcessErrorStateRecord.appNotResponding()
    ↓
ActivityManagerService.dumpStackTraces()
    ↓
Process.sendSignal(pid, SIGNAL_QUIT)
    ↓
android_os_Process_sendSignalQuiet() [JNI]
    ↓
kill(pid, SIGQUIT) [系统调用]
```

### 6.2 应用进程端

```
接收SIGQUIT信号
    ↓
SignalCatcher.HandleSigQuit() [信号处理器]
    ↓
写入pipe唤醒SignalCatcher线程
    ↓
SignalCatcher::Run() [守护线程]
    ↓
创建DumpWatchdog(10秒)
    ↓
打开/data/anr/traces.txt
    ↓
ThreadList::DumpForSigQuit()
    ↓
遍历所有线程，dump堆栈
    ↓
[如果超时] Watchdog中断dump
    ↓
关闭文件，完成
```

---

## 七、常见问题和调试技巧

### 7.1 为什么有时traces文件不完整？

**可能原因**：
1. 10秒超时触发，dump被中断
2. 文件权限问题，无法写入
3. 磁盘空间不足
4. 进程已经完全死锁，连信号处理都无法执行

### 7.2 如何调试Signal 3处理？

```bash
# 手动发送Signal 3
adb shell kill -3 <pid>

# 查看traces文件
adb shell cat /data/anr/traces.txt

# 监控signal处理
adb logcat | grep -i "signal\|sigquit\|anr"
```

### 7.3 如何验证Watchdog机制？

可以在应用中故意制造一个极慢的线程堆栈dump：

```java
// 在应用的SignalCatcher中添加延时
// 注意：这需要修改系统框架，仅用于测试
Thread.sleep(15000); // 超过10秒
```

观察traces文件是否包含"INTERRUPTED - timeout"标记。

---

## 八、性能考虑

### 8.1 Signal 3的性能影响

- **暂停时间**：Dump堆栈时，所有线程需要暂停
- **CPU消耗**：遍历所有线程和堆栈帧
- **I/O消耗**：写入traces文件（可能几MB）
- **对用户的影响**：应用可能出现短暂卡顿

### 8.2 优化建议

1. **增量dump**：优先dump主线程和关键线程
2. **压缩输出**：对堆栈信息进行压缩
3. **异步上传**：不阻塞主流程
4. **采样策略**：高频ANR时，降低dump频率

---

## 九、Android版本差异

不同Android版本在实现上有细微差异：

| 版本 | 主要变化 |
|------|---------|
| Android 8.0- | 使用简单的alarm机制 |
| Android 9.0 | 引入更精细的超时控制 |
| Android 10.0 | 优化traces文件格式 |
| Android 11.0 | 增加native crash信息 |
| Android 12.0+ | 使用Watchdog线程，更可靠 |

---

## 十、总结

ANR信号处理机制的核心要点：

1. **Signal 3的作用**：触发应用dump线程堆栈到traces文件
2. **异步处理**：信号处理器只负责唤醒专门的SignalCatcher线程
3. **超时保护**：10秒Watchdog确保不会无限期阻塞
4. **协作机制**：system_server和应用进程通过文件大小变化通信
5. **优雅降级**：即使超时，也能保存部分有用信息

这套机制平衡了以下矛盾：
- ✅ 收集完整的调试信息 vs ⏱️ 不过度延长ANR处理时间
- ✅ 等待应用响应 vs ⚠️ 避免system_server被拖住
- ✅ 详细的堆栈信息 vs 📁 控制文件大小

通过精心设计的多层超时机制和守护线程，Android确保了ANR处理的健壮性和可靠性。
