# ANR处理流程详解：从appnotResponding到Signal恢复机制

## 概述

本文档详细解释Android系统中ANR（Application Not Responding）的完整处理流程，包括：
1. `processErrorState`的`appnotResponding`方法触发
2. Signal 3 (SIGQUIT)的发送和处理
3. 应用层回调机制
4. 守护线程sigaction 10秒恢复机制

---

## 一、ANR检测和触发流程

### 1.1 ANR检测机制

Android系统通过多种机制检测ANR：
- **Input事件超时**：5秒内未响应输入事件
- **BroadcastReceiver超时**：10秒（前台）或60秒（后台）内未完成
- **Service超时**：20秒内未启动完成
- **ContentProvider超时**：10秒内未发布完成

### 1.2 processErrorState.appnotResponding入口

当检测到ANR时，系统会调用`ActivityManagerService.processErrorState()`方法中的`appnotResponding()`方法。

**关键代码位置**：`frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`

```java
final void appNotResponding(ProcessRecord app, ActivityRecord activity,
        ActivityRecord parent, boolean aboveSystem, final String annotation) {
    // 1. 记录ANR信息
    app.mErrorState.setAppNotResponding(annotation);
    
    // 2. 收集ANR信息（堆栈、进程状态等）
    StringWriter sw = new StringWriter();
    PrintWriter pw = new FastPrintWriter(sw, false, 1024);
    pw.println(annotation);
    pw.println("PID: " + app.pid);
    
    // 3. 获取主线程堆栈
    app.mErrorState.dumpDebug(sw, null);
    
    // 4. 发送Signal 3 (SIGQUIT)到目标进程
    sendSignalToProcess(app.pid, Process.SIGNAL_QUIT);
    
    // 5. 启动ANR处理流程
    mAnrHelper.appNotResponding(app, activity, parent, aboveSystem, annotation);
}
```

---

## 二、Signal 3 (SIGQUIT) 发送流程

### 2.1 Signal发送机制

**关键代码位置**：`frameworks/base/core/java/android/os/Process.java`

```java
public static final int SIGNAL_QUIT = 3;  // SIGQUIT

public static final void sendSignal(int pid, int signal) {
    sendSignalQuiet(pid, signal);
}

public static final native void sendSignalQuiet(int pid, int signal);
```

**Native层实现**：`frameworks/base/core/jni/android_util_Process.cpp`

```cpp
static void android_os_Process_sendSignalQuiet(JNIEnv* env, jobject clazz, jint pid, jint sig) {
    ALOGI("Sending signal. PID: %d SIG: %d", pid, sig);
    if (pid > 0) {
        ALOGI("kill(%d, %d) = %d", pid, sig, kill(pid, sig));
    }
}
```

### 2.2 Signal发送时机

在`appNotResponding`方法中，系统会：
1. **立即发送SIGQUIT**：用于触发应用dump堆栈信息
2. **设置超时机制**：等待应用响应，如果10秒内无响应则采取进一步措施

---

## 三、应用层Signal处理机制

### 3.1 Signal Handler注册

Android应用在启动时会注册Signal Handler来处理SIGQUIT信号。

**关键代码位置**：`frameworks/base/core/jni/AndroidRuntime.cpp`

```cpp
// 在AndroidRuntime::start()中注册
static void sigquit_handler(int sig) {
    // 1. 获取当前线程信息
    // 2. Dump所有线程的堆栈
    // 3. 写入到ANR trace文件
    // 4. 通知系统已处理
}
```

### 3.2 Signal处理流程

当应用收到SIGQUIT信号时：

```cpp
// frameworks/base/core/jni/AndroidRuntime.cpp
static void sigquit_handler(int sig) {
    ALOGI("*** SIGQUIT received, dumping threads ***");
    
    // 1. 获取所有线程的堆栈信息
    std::string stack_trace = DumpThreadStacks();
    
    // 2. 写入ANR trace文件
    // 路径：/data/anr/traces.txt 或 /data/anr/traces_<pid>.txt
    WriteAnrTrace(stack_trace);
    
    // 3. 通知系统已处理（通过Binder回调）
    NotifyAnrHandled();
}
```

### 3.3 ANR Trace文件生成

**文件位置**：
- `/data/anr/traces.txt`（旧版本）
- `/data/anr/traces_<pid>.txt`（新版本）

**内容包含**：
- 所有线程的堆栈信息
- 线程状态（RUNNABLE, BLOCKED, WAITING等）
- 锁信息
- Native堆栈

---

## 四、守护线程Sigaction恢复机制

### 4.1 问题背景

当应用处理SIGQUIT时，如果应用处于阻塞状态（如死锁），可能无法及时响应。为了防止这种情况，系统实现了**守护线程机制**。

### 4.2 守护线程创建

**关键代码位置**：`frameworks/base/services/core/java/com/android/server/am/AnrHelper.java`

```java
class AnrHelper {
    private static final int ANR_TIMEOUT_MS = 10000; // 10秒超时
    
    // 守护线程，用于监控ANR处理状态
    private class AnrMonitorThread extends Thread {
        private final ProcessRecord mApp;
        private final long mStartTime;
        
        AnrMonitorThread(ProcessRecord app) {
            super("AnrMonitor-" + app.pid);
            mApp = app;
            mStartTime = SystemClock.uptimeMillis();
        }
        
        @Override
        public void run() {
            try {
                // 等待10秒
                Thread.sleep(ANR_TIMEOUT_MS);
                
                // 检查应用是否已响应
                if (!mApp.mErrorState.hasResponded()) {
                    // 应用未响应，执行恢复机制
                    recoverFromAnr(mApp);
                }
            } catch (InterruptedException e) {
                // 被中断，说明应用已响应
            }
        }
    }
}
```

### 4.3 Sigaction恢复机制原理

#### 4.3.1 信号拦截和恢复

在发送SIGQUIT之前，系统会：
1. **保存原始sigaction**：记录应用当前的SIGQUIT处理方式
2. **设置临时sigaction**：确保信号能被正确处理
3. **10秒后恢复**：如果应用正常响应，恢复原始sigaction

**关键代码位置**：`frameworks/base/core/jni/android_util_Process.cpp`

```cpp
// 保存原始sigaction
struct sigaction old_sigquit_action;
sigaction(SIGQUIT, NULL, &old_sigquit_action);

// 设置新的sigaction（用于ANR处理）
struct sigaction new_sigquit_action;
new_sigquit_action.sa_handler = anr_signal_handler;
new_sigquit_action.sa_flags = SA_ONSTACK;
sigaction(SIGQUIT, &new_sigquit_action, NULL);

// 发送SIGQUIT
kill(pid, SIGQUIT);

// 启动恢复线程（10秒后恢复）
pthread_t restore_thread;
pthread_create(&restore_thread, NULL, restore_sigaction_after_timeout, &old_sigquit_action);
```

#### 4.3.2 恢复线程实现

```cpp
void* restore_sigaction_after_timeout(void* arg) {
    struct sigaction* old_action = (struct sigaction*)arg;
    
    // 等待10秒
    sleep(10);
    
    // 检查ANR是否已处理
    if (anr_handled) {
        // 恢复原始sigaction
        sigaction(SIGQUIT, old_action, NULL);
        ALOGI("Restored original SIGQUIT handler");
    } else {
        // ANR未处理，可能需要强制kill
        ALOGE("ANR not handled, may need to kill process");
    }
    
    return NULL;
}
```

### 4.4 完整时序图

```
时间轴：
T0: ANR检测触发
    ↓
T1: processErrorState.appnotResponding()调用
    ↓
T2: 保存原始sigaction
    ↓
T3: 设置新的SIGQUIT handler
    ↓
T4: 发送SIGQUIT到应用进程
    ↓
T5: 启动守护线程（10秒倒计时）
    ↓
T6: 应用收到SIGQUIT，执行handler
    ↓
T7: 应用dump堆栈，写入trace文件
    ↓
T8: 应用通知系统已处理（通过Binder）
    ↓
T9: 系统标记ANR已处理
    ↓
T10: 守护线程检查到已处理，恢复原始sigaction
    ↓
T11: 如果10秒内未处理，守护线程执行恢复/强制kill
```

---

## 五、关键机制详解

### 5.1 为什么需要10秒恢复机制？

1. **防止信号丢失**：如果应用长时间阻塞，可能无法处理SIGQUIT
2. **资源保护**：避免信号handler被永久替换
3. **系统稳定性**：确保系统能够从ANR状态恢复

### 5.2 Sigaction恢复的作用

1. **恢复应用原始行为**：应用可能有自己的SIGQUIT处理逻辑
2. **避免干扰**：防止ANR处理机制影响应用的正常运行
3. **状态一致性**：确保系统状态的一致性

### 5.3 异常情况处理

如果10秒内应用未响应：

```java
private void recoverFromAnr(ProcessRecord app) {
    // 1. 尝试再次发送SIGQUIT
    Process.sendSignal(app.pid, Process.SIGNAL_QUIT);
    
    // 2. 等待额外时间（如2秒）
    Thread.sleep(2000);
    
    // 3. 如果仍未响应，强制kill
    if (!app.mErrorState.hasResponded()) {
        app.kill("ANR timeout - no response", true);
    }
    
    // 4. 恢复sigaction
    restoreOriginalSigaction(app.pid);
}
```

---

## 六、回调机制

### 6.1 ANR处理完成回调

应用处理完SIGQUIT后，通过Binder回调通知系统：

```java
// frameworks/base/core/java/android/os/Process.java
public static void notifyAnrHandled(int pid) {
    try {
        ActivityManagerService.getService().notifyAnrHandled(pid);
    } catch (RemoteException e) {
        // 处理异常
    }
}
```

### 6.2 系统端接收回调

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java
public void notifyAnrHandled(int pid) {
    synchronized (mPidsSelfLocked) {
        ProcessRecord app = mPidsSelfLocked.get(pid);
        if (app != null) {
            app.mErrorState.setAnrHandled();
            // 取消守护线程
            mAnrHelper.cancelMonitor(app);
        }
    }
}
```

---

## 七、总结

### 7.1 完整流程总结

1. **ANR检测** → 触发`appnotResponding()`
2. **信号准备** → 保存原始sigaction，设置新handler
3. **信号发送** → 发送SIGQUIT到应用进程
4. **守护线程** → 启动10秒倒计时监控
5. **应用处理** → 应用收到信号，dump堆栈，写入trace文件
6. **回调通知** → 应用通过Binder通知系统已处理
7. **恢复机制** → 守护线程检测到处理完成，恢复原始sigaction
8. **异常处理** → 如果10秒内未响应，执行强制恢复或kill

### 7.2 关键设计点

- **非阻塞设计**：通过守护线程避免阻塞主流程
- **状态恢复**：确保系统状态的一致性
- **容错机制**：处理应用无法响应的情况
- **资源保护**：防止信号handler被永久替换

---

## 参考资料

- Android源码：`frameworks/base/services/core/java/com/android/server/am/`
- Android源码：`frameworks/base/core/jni/`
- Linux Signal机制：`man 2 sigaction`
- ANR Trace文件格式：`/data/anr/traces.txt`
