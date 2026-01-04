# ANR处理机制代码实现细节

## 一、核心类和方法

### 1.1 ActivityManagerService.appNotResponding()

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

final void appNotResponding(ProcessRecord app, ActivityRecord activity,
        ActivityRecord parent, boolean aboveSystem, final String annotation) {
    
    // 步骤1: 更新错误状态
    app.mErrorState.setAppNotResponding(annotation);
    
    // 步骤2: 记录ANR时间
    long anrTime = SystemClock.uptimeMillis();
    app.mErrorState.setAnrTime(anrTime);
    
    // 步骤3: 收集进程信息
    StringBuilder info = new StringBuilder();
    info.append("ANR in ").append(app.processName);
    if (activity != null && activity.shortComponentName != null) {
        info.append(" (").append(activity.shortComponentName).append(")");
    }
    info.append("\n");
    info.append("PID: ").append(app.pid).append("\n");
    info.append("Reason: ").append(annotation).append("\n");
    
    // 步骤4: 发送SIGQUIT信号
    // 这会触发应用dump堆栈
    Process.sendSignal(app.pid, Process.SIGNAL_QUIT);
    
    // 步骤5: 启动ANR处理流程
    mAnrHelper.appNotResponding(app, activity, parent, aboveSystem, annotation);
    
    // 步骤6: 记录ANR日志
    Slog.e(TAG, info.toString());
}
```

### 1.2 AnrHelper.appNotResponding()

```java
// frameworks/base/services/core/java/com/android/server/am/AnrHelper.java

public void appNotResponding(ProcessRecord app, ActivityRecord activity,
        ActivityRecord parent, boolean aboveSystem, String annotation) {
    
    // 步骤1: 创建ANR监控线程
    AnrMonitorThread monitorThread = new AnrMonitorThread(app);
    
    // 步骤2: 设置信号处理前的准备工作
    prepareSignalHandling(app.pid);
    
    // 步骤3: 启动监控线程（10秒超时）
    monitorThread.start();
    
    // 步骤4: 记录ANR信息到系统日志
    logAnrInfo(app, activity, annotation);
    
    // 步骤5: 通知系统UI显示ANR对话框（如果需要）
    if (aboveSystem) {
        showAnrDialog(app, activity, annotation);
    }
}
```

### 1.3 AnrMonitorThread（守护线程）

```java
// frameworks/base/services/core/java/com/android/server/am/AnrHelper.java

private class AnrMonitorThread extends Thread {
    private static final int ANR_TIMEOUT_MS = 10000; // 10秒
    private final ProcessRecord mApp;
    private final long mStartTime;
    private volatile boolean mCancelled = false;
    
    AnrMonitorThread(ProcessRecord app) {
        super("AnrMonitor-" + app.pid);
        setDaemon(true); // 设置为守护线程
        mApp = app;
        mStartTime = SystemClock.uptimeMillis();
    }
    
    @Override
    public void run() {
        try {
            // 等待10秒
            Thread.sleep(ANR_TIMEOUT_MS);
            
            synchronized (mApp) {
                // 检查是否已被取消（应用已响应）
                if (mCancelled) {
                    return;
                }
                
                // 检查应用是否已处理ANR
                if (!mApp.mErrorState.hasResponded()) {
                    // 应用未响应，执行恢复机制
                    Slog.w(TAG, "ANR timeout: Process " + mApp.pid + 
                          " did not respond within " + ANR_TIMEOUT_MS + "ms");
                    
                    recoverFromAnr(mApp);
                } else {
                    // 应用已响应，恢复原始sigaction
                    restoreOriginalSigaction(mApp.pid);
                }
            }
        } catch (InterruptedException e) {
            // 被中断，说明应用已响应或需要取消
            Slog.d(TAG, "AnrMonitorThread interrupted for pid " + mApp.pid);
        }
    }
    
    public void cancel() {
        mCancelled = true;
        interrupt();
    }
}
```

## 二、Native层Signal处理

### 2.1 Signal发送（JNI）

```cpp
// frameworks/base/core/jni/android_util_Process.cpp

static void android_os_Process_sendSignalQuiet(JNIEnv* env, jobject clazz, 
                                                jint pid, jint sig) {
    if (pid > 0) {
        int result = kill(pid, sig);
        if (result != 0) {
            ALOGE("Failed to send signal %d to process %d: %s", 
                  sig, pid, strerror(errno));
        } else {
            ALOGI("Sent signal %d to process %d", sig, pid);
        }
    }
}
```

### 2.2 Signal Handler设置和恢复

```cpp
// frameworks/base/core/jni/android_util_Process.cpp

// 保存原始sigaction的全局变量
static struct sigaction g_original_sigquit_action;
static bool g_sigquit_action_saved = false;
static pthread_mutex_t g_sigaction_mutex = PTHREAD_MUTEX_INITIALIZER;

// 准备信号处理（在发送SIGQUIT之前调用）
static void prepare_signal_handling(jint pid) {
    pthread_mutex_lock(&g_sigaction_mutex);
    
    // 保存原始sigaction（如果尚未保存）
    if (!g_sigquit_action_saved) {
        if (sigaction(SIGQUIT, NULL, &g_original_sigquit_action) == 0) {
            g_sigquit_action_saved = true;
            ALOGI("Saved original SIGQUIT handler for pid %d", pid);
        }
    }
    
    // 设置新的sigaction用于ANR处理
    struct sigaction new_action;
    memset(&new_action, 0, sizeof(new_action));
    new_action.sa_handler = anr_signal_handler;
    new_action.sa_flags = SA_ONSTACK | SA_RESTART;
    sigemptyset(&new_action.sa_mask);
    
    if (sigaction(SIGQUIT, &new_action, NULL) == 0) {
        ALOGI("Set ANR signal handler for pid %d", pid);
    }
    
    pthread_mutex_unlock(&g_sigaction_mutex);
}

// ANR信号处理函数
static void anr_signal_handler(int sig) {
    if (sig == SIGQUIT) {
        ALOGI("*** SIGQUIT received for ANR, dumping threads ***");
        
        // 获取当前进程ID
        pid_t pid = getpid();
        
        // Dump所有线程的堆栈
        dump_all_thread_stacks(pid);
        
        // 通知Java层ANR已处理
        notify_anr_handled(pid);
    }
}

// 恢复原始sigaction
static void restore_original_sigaction(jint pid) {
    pthread_mutex_lock(&g_sigaction_mutex);
    
    if (g_sigquit_action_saved) {
        if (sigaction(SIGQUIT, &g_original_sigquit_action, NULL) == 0) {
            ALOGI("Restored original SIGQUIT handler for pid %d", pid);
            g_sigquit_action_saved = false;
        } else {
            ALOGE("Failed to restore original SIGQUIT handler: %s", 
                  strerror(errno));
        }
    }
    
    pthread_mutex_unlock(&g_sigaction_mutex);
}

// 延迟恢复sigaction的线程函数
static void* restore_sigaction_after_timeout(void* arg) {
    jint pid = *(jint*)arg;
    
    // 等待10秒
    sleep(10);
    
    // 检查ANR是否已处理
    if (is_anr_handled(pid)) {
        // 已处理，恢复原始sigaction
        restore_original_sigaction(pid);
    } else {
        // 未处理，可能需要强制恢复
        ALOGW("ANR not handled for pid %d after 10s, forcing restore", pid);
        restore_original_sigaction(pid);
    }
    
    return NULL;
}
```

### 2.3 堆栈Dump实现

```cpp
// frameworks/base/core/jni/AndroidRuntime.cpp

static void dump_all_thread_stacks(pid_t pid) {
    // 打开trace文件
    char trace_file[256];
    snprintf(trace_file, sizeof(trace_file), 
             "/data/anr/traces_%d.txt", pid);
    
    FILE* fp = fopen(trace_file, "a");
    if (!fp) {
        ALOGE("Failed to open trace file: %s", trace_file);
        return;
    }
    
    // 写入时间戳
    time_t now = time(NULL);
    fprintf(fp, "----- pid %d at %s -----\n", pid, ctime(&now));
    
    // 遍历所有线程
    DIR* proc_dir = opendir("/proc/self/task");
    if (proc_dir) {
        struct dirent* entry;
        while ((entry = readdir(proc_dir)) != NULL) {
            if (entry->d_name[0] == '.') continue;
            
            int tid = atoi(entry->d_name);
            if (tid > 0) {
                dump_thread_stack(fp, tid);
            }
        }
        closedir(proc_dir);
    }
    
    fclose(fp);
    ALOGI("Dumped thread stacks to %s", trace_file);
}

static void dump_thread_stack(FILE* fp, int tid) {
    char stack_file[256];
    snprintf(stack_file, sizeof(stack_file), 
             "/proc/self/task/%d/stack", tid);
    
    FILE* stack_fp = fopen(stack_file, "r");
    if (stack_fp) {
        fprintf(fp, "\n----- thread %d -----\n", tid);
        char line[1024];
        while (fgets(line, sizeof(line), stack_fp)) {
            fputs(line, fp);
        }
        fclose(stack_fp);
    }
}
```

## 三、恢复机制实现

### 3.1 recoverFromAnr()方法

```java
// frameworks/base/services/core/java/com/android/server/am/AnrHelper.java

private void recoverFromAnr(ProcessRecord app) {
    Slog.w(TAG, "Recovering from ANR for pid " + app.pid);
    
    // 步骤1: 再次尝试发送SIGQUIT（可能应用刚恢复）
    try {
        Process.sendSignal(app.pid, Process.SIGNAL_QUIT);
        Thread.sleep(2000); // 等待2秒
        
        if (app.mErrorState.hasResponded()) {
            // 应用已响应，恢复sigaction
            restoreOriginalSigaction(app.pid);
            return;
        }
    } catch (Exception e) {
        Slog.e(TAG, "Error sending second SIGQUIT", e);
    }
    
    // 步骤2: 检查进程是否还存在
    if (!isProcessAlive(app.pid)) {
        Slog.i(TAG, "Process " + app.pid + " already dead");
        return;
    }
    
    // 步骤3: 强制恢复sigaction（防止信号handler被永久替换）
    restoreOriginalSigaction(app.pid);
    
    // 步骤4: 根据策略决定是否kill进程
    if (shouldKillProcess(app)) {
        app.kill("ANR timeout - no response after recovery", true);
    } else {
        // 记录ANR但保留进程
        recordAnrEvent(app);
    }
}

private boolean isProcessAlive(int pid) {
    try {
        Process.sendSignal(pid, 0); // 发送0信号检查进程是否存在
        return true;
    } catch (Exception e) {
        return false;
    }
}

private boolean shouldKillProcess(ProcessRecord app) {
    // 根据应用类型和ANR次数决定是否kill
    if (app.mErrorState.getAnrCount() > 3) {
        return true; // 多次ANR，kill进程
    }
    
    if (app.isPersistent()) {
        return false; // 系统进程，不kill
    }
    
    return true; // 默认kill
}
```

### 3.2 restoreOriginalSigaction()实现

```java
// frameworks/base/services/core/java/com/android/server/am/AnrHelper.java

private void restoreOriginalSigaction(int pid) {
    try {
        // 调用native方法恢复sigaction
        Process.restoreSigaction(pid);
        Slog.d(TAG, "Restored original sigaction for pid " + pid);
    } catch (Exception e) {
        Slog.e(TAG, "Failed to restore sigaction for pid " + pid, e);
    }
}
```

```cpp
// frameworks/base/core/jni/android_util_Process.cpp

static void android_os_Process_restoreSigaction(JNIEnv* env, jobject clazz, jint pid) {
    restore_original_sigaction(pid);
}
```

## 四、回调机制实现

### 4.1 应用层通知系统

```java
// frameworks/base/core/java/android/os/Process.java

public static void notifyAnrHandled(int pid) {
    try {
        IActivityManager am = ActivityManager.getService();
        if (am != null) {
            am.notifyAnrHandled(pid);
        }
    } catch (RemoteException e) {
        Log.e(TAG, "Failed to notify ANR handled", e);
    }
}
```

### 4.2 系统端接收回调

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

@Override
public void notifyAnrHandled(int pid) {
    synchronized (mPidsSelfLocked) {
        ProcessRecord app = mPidsSelfLocked.get(pid);
        if (app != null) {
            // 标记ANR已处理
            app.mErrorState.setAnrHandled();
            
            // 取消守护线程
            mAnrHelper.cancelMonitor(app);
            
            // 记录处理时间
            long handleTime = SystemClock.uptimeMillis();
            long anrDuration = handleTime - app.mErrorState.getAnrTime();
            Slog.i(TAG, "ANR handled for pid " + pid + 
                  " in " + anrDuration + "ms");
        }
    }
}
```

### 4.3 取消监控线程

```java
// frameworks/base/services/core/java/com/android/server/am/AnrHelper.java

public void cancelMonitor(ProcessRecord app) {
    synchronized (mMonitors) {
        AnrMonitorThread monitor = mMonitors.remove(app.pid);
        if (monitor != null) {
            monitor.cancel();
            Slog.d(TAG, "Cancelled ANR monitor for pid " + app.pid);
        }
    }
}
```

## 五、关键数据结构

### 5.1 ProcessRecord.mErrorState

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessErrorStateRecord.java

class ProcessErrorStateRecord {
    private boolean mAppNotResponding = false;
    private String mAppNotRespondingReport;
    private long mAnrTime = 0;
    private boolean mAnrHandled = false;
    private int mAnrCount = 0;
    
    void setAppNotResponding(String report) {
        mAppNotResponding = true;
        mAppNotRespondingReport = report;
        mAnrTime = SystemClock.uptimeMillis();
        mAnrHandled = false;
        mAnrCount++;
    }
    
    void setAnrHandled() {
        mAnrHandled = true;
    }
    
    boolean hasResponded() {
        return mAnrHandled;
    }
    
    long getAnrTime() {
        return mAnrTime;
    }
    
    int getAnrCount() {
        return mAnrCount;
    }
}
```

## 六、时序图

```
[ANR检测] → [appNotResponding()]
    ↓
[保存原始sigaction] → [设置新sigaction]
    ↓
[发送SIGQUIT] → [启动守护线程(10s)]
    ↓
[应用收到SIGQUIT] → [执行handler]
    ↓
[Dump堆栈] → [写入trace文件]
    ↓
[通知系统已处理] → [标记mAnrHandled=true]
    ↓
[守护线程检查] → [恢复原始sigaction]
    ↓
[完成]
```

## 七、异常情况处理

### 7.1 应用无法响应SIGQUIT

如果应用处于深度阻塞状态（如死锁），可能无法处理SIGQUIT：

1. **10秒超时**：守护线程检测到未响应
2. **强制恢复**：恢复原始sigaction，防止信号handler被永久替换
3. **可选kill**：根据策略决定是否kill进程

### 7.2 多次ANR处理

系统会记录ANR次数，如果频繁ANR：
- 超过3次：强制kill进程
- 系统进程：不kill，但记录日志
- 普通应用：kill并重启

### 7.3 进程已死亡

如果进程在ANR处理过程中死亡：
- 检测到进程不存在
- 清理相关资源
- 记录ANR事件但不执行恢复
