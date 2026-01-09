# ANR 详细调用路径分析

## 核心问题澄清

用户问到的 `@Override appNotResponding(String reason)` 和**输入ANR**是**两条不同的路径**！

---

## 一、AMS中的多个 appNotResponding 方法对比

```java
// ActivityManagerService.java 中有多个 appNotResponding 相关方法：

// ========== 路径1: 应用主动上报ANR（AIDL接口实现）==========
@Override  // 实现 IActivityManager.aidl 接口
public void appNotResponding(final String reason) {
    // 这是应用自己调用的！不是输入ANR的路径
}

// ========== 路径2: 输入ANR（Input dispatching timeout）==========
public boolean inputDispatchingTimedOut(ProcessRecord proc, ...) {
    // 这才是输入ANR的入口！
}

// ========== 路径3: 内部调用（通过ProcessRecord）==========
void appNotResponding(@NonNull ProcessRecord anrProcess, @NonNull TimeoutRecord timeoutRecord) {
    // 内部使用
}
```

---

## 二、输入ANR的真正调用路径

**输入ANR 不走 `@Override appNotResponding(String reason)`！**

真正的调用链是：

```
┌─────────────────────────────────────────────────────────────────────┐
│ Native层                                                             │
│ InputDispatcher.onAnrLocked()                                        │
│         ↓                                                            │
│ mPolicy->notifyAnr()  (NativeInputManager)                          │
│         ↓ [JNI回调]                                                  │
└─────────────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Java层                                                               │
│                                                                      │
│ InputManagerService                                                  │
│   .notifyAnr()  [native callback]                                   │
│         ↓                                                            │
│ WindowManagerCallbacks                                               │
│   .notifyAnr()                                                       │
│         ↓                                                            │
│ InputManagerCallback (WMS持有)                                       │
│   .notifyAnr()                                                       │
│         ↓                                                            │
│ AnrController                                                        │
│   .notifyAnr()                                                       │
│         ↓                                                            │
│ ⭐ ActivityManagerService                                            │
│   .inputDispatchingTimedOut()  ← 注意：是这个方法！不是appNotResponding │
│         ↓                                                            │
│ AnrHelper                                                            │
│   .appNotResponding()                                                │
│         ↓                                                            │
│ ProcessRecord                                                        │
│   .appNotResponding()                                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、详细代码分析

### 3.1 AnrController.notifyAnr()

```java
// frameworks/base/services/core/java/com/android/server/wm/AnrController.java

class AnrController {
    
    private final ActivityTaskManagerService mAtmService;
    
    /**
     * 被 InputManagerCallback 调用
     * 处理输入ANR
     */
    long notifyAnr(@NonNull ActivityRecord activity,
                   @NonNull WindowState windowState,
                   String reason) {
        
        // 1. 获取进程信息
        final int pid = windowState.mSession.mPid;
        final int uid = windowState.mSession.mUid;
        final String processName = windowState.mSession.mProcessName;
        
        // 2. 检查进程状态
        if (isProcessFrozen(pid)) {
            // 冻结的进程，解冻后重试
            unfreezeProcess(pid);
            return INPUT_DISPATCHING_TIMEOUT_MILLIS; // 返回新的超时时间
        }
        
        // 3. 构建超时记录
        TimeoutRecord timeoutRecord = TimeoutRecord.forInputDispatch(reason);
        
        // 4. ⭐ 调用 ActivityManagerService.inputDispatchingTimedOut() ⭐
        //    注意：不是调用 appNotResponding()！
        boolean abort = mAtmService.mAmInternal.inputDispatchingTimedOut(
                pid,
                windowState.mAboveInsetsState,
                timeoutRecord);
        
        if (abort) {
            return 0; // 返回0表示不再等待
        }
        
        return INPUT_DISPATCHING_TIMEOUT_MILLIS; // 返回新的超时继续等待
    }
}
```

### 3.2 ActivityManagerService.inputDispatchingTimedOut()

**这才是输入ANR的真正入口！**

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

public class ActivityManagerService extends IActivityManager.Stub {
    
    /**
     * 输入分发超时 - 被 AnrController 调用
     * 这是输入ANR的入口点！
     */
    public boolean inputDispatchingTimedOut(int pid,
                                             boolean aboveSystem,
                                             TimeoutRecord timeoutRecord) {
        ProcessRecord proc;
        
        // 1. 根据PID查找进程
        synchronized (mPidsSelfLocked) {
            proc = mPidsSelfLocked.get(pid);
        }
        
        if (proc == null) {
            Slog.w(TAG, "Timeout for unknown process pid=" + pid);
            return false;
        }
        
        // 2. 调用带ProcessRecord的重载方法
        return inputDispatchingTimedOut(proc, null /* activity */, 
                                        null /* parent */,
                                        aboveSystem, timeoutRecord);
    }
    
    /**
     * 核心处理方法
     */
    public boolean inputDispatchingTimedOut(final ProcessRecord proc,
                                             final ActivityRecord activity,
                                             final ActivityRecord parent,
                                             final boolean aboveSystem,
                                             final TimeoutRecord timeoutRecord) {
        
        // 1. 检查是否正在调试
        if (proc.isDebugging()) {
            Slog.i(TAG, "Input dispatching timed out but process is debugging");
            return false; // 不处理ANR
        }
        
        // 2. 检查是否有instrumentation
        if (proc.getActiveInstrumentation() != null) {
            Bundle info = new Bundle();
            info.putString("reason", timeoutRecord.mReason);
            finishInstrumentationLocked(proc, Activity.RESULT_CANCELED, info);
            return true;
        }
        
        // 3. ⭐ 调用 AnrHelper.appNotResponding() ⭐
        mAnrHelper.appNotResponding(proc, 
                                     activity, 
                                     parent != null ? parent.info : null,
                                     activity != null ? activity.info : null,
                                     null /* description */,
                                     aboveSystem,
                                     timeoutRecord,
                                     false /* isContinuousAnr */);
        
        return true;
    }
}
```

### 3.3 AnrHelper.appNotResponding()

```java
// frameworks/base/services/core/java/com/android/server/am/AnrHelper.java

class AnrHelper {
    
    private final ActivityManagerService mService;
    private final Handler mAnrHandler;
    private final ArrayList<AnrRecord> mAnrRecords = new ArrayList<>();
    
    /**
     * 输入ANR进入这里
     * 创建AnrRecord并加入队列
     */
    void appNotResponding(ProcessRecord anrProcess,
                          ActivityRecord activity,
                          ApplicationInfo appInfo,
                          ActivityInfo activityInfo,
                          String description,
                          boolean aboveSystem,
                          TimeoutRecord timeoutRecord,
                          boolean isContinuousAnr) {
        
        // 1. 创建ANR记录
        AnrRecord anrRecord = new AnrRecord(
            anrProcess,          // 进程
            activity,            // 触发ANR的Activity
            activityInfo,        // Activity信息
            description,         // 描述
            aboveSystem,         // 是否在系统之上
            timeoutRecord,       // 超时记录（包含原因）
            isContinuousAnr      // 是否持续ANR
        );
        
        // 2. 加入ANR记录队列
        synchronized (mAnrRecords) {
            mAnrRecords.add(anrRecord);
        }
        
        // 3. 发送消息到ANR处理Handler
        //    使用单独的线程处理ANR，避免阻塞主流程
        mAnrHandler.sendEmptyMessage(PROCESS_ANR_MSG);
    }
    
    /**
     * ANR处理Handler收到消息后执行
     */
    private void processAnr() {
        AnrRecord record;
        
        synchronized (mAnrRecords) {
            if (mAnrRecords.isEmpty()) {
                return;
            }
            record = mAnrRecords.remove(0);
        }
        
        // 4. ⭐ 调用 ProcessRecord.appNotResponding() ⭐
        //    这里才是真正执行ANR处理的地方！
        record.mAnrProcess.mErrorState.appNotResponding(
            record.mActivityShortComponentName,
            record.mAppInfo,
            record.mDescription,
            record.mAboveSystem,
            record.mTimeoutRecord,
            record.mIsContinuousAnr
        );
    }
}
```

---

## 四、@Override appNotResponding(String reason) 是干什么的？

这个方法是 **IActivityManager.aidl** 接口的实现，用于**应用自己主动上报ANR**！

### 4.1 AIDL接口定义

```aidl
// frameworks/base/core/java/android/app/IActivityManager.aidl

interface IActivityManager {
    // ... 其他方法 ...
    
    /**
     * 应用自己报告ANR
     * 由应用进程调用
     */
    void appNotResponding(String reason);
}
```

### 4.2 使用场景

```java
// 应用代码中（例如某个卡顿检测库）
ActivityManager am = context.getSystemService(ActivityManager.class);
// 通过Binder调用到AMS
IActivityManager.appNotResponding("Custom ANR: Main thread blocked for 10s");
```

### 4.3 AMS中的实现

```java
// ActivityManagerService.java

@Override  // 实现 IActivityManager.aidl
public void appNotResponding(final String reason) {
    // 转发到带boolean参数的重载
    appNotResponding(reason, /*isContinuousAnr*/ false);
}

public void appNotResponding(final String reason, boolean isContinuousAnr) {
    TimeoutRecord timeoutRecord = TimeoutRecord.forApp("App requested: " + reason);
    
    // 通过Binder调用者的PID找到进程
    final int callingPid = Binder.getCallingPid();  // ⭐ 获取调用方PID
    
    timeoutRecord.mLatencyTracker.waitingOnPidLockStarted();
    synchronized (mPidsSelfLocked) {
        timeoutRecord.mLatencyTracker.waitingOnPidLockEnded();
        
        // 根据PID查找ProcessRecord
        final ProcessRecord app = mPidsSelfLocked.get(callingPid);
        if (app == null) {
            throw new SecurityException("Unknown process: " + callingPid);
        }
        
        Slog.d(TAG, "ZYY anr埋点");  // 用户添加的日志
        
        // 最终还是走到 AnrHelper
        mAnrHelper.appNotResponding(app, null, app.info, null, null, false,
                timeoutRecord, isContinuousAnr);
    }
}
```

---

## 五、两条路径对比

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         路径1: 输入ANR（系统触发）                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  InputDispatcher (Native, 5秒超时检测)                                      │
│          ↓                                                                 │
│  NativeInputManager.notifyAnr()                                            │
│          ↓ [JNI]                                                           │
│  InputManagerService.notifyAnr()                                           │
│          ↓                                                                 │
│  InputManagerCallback.notifyAnr()                                          │
│          ↓                                                                 │
│  AnrController.notifyAnr()                                                 │
│          ↓                                                                 │
│  ⭐ AMS.inputDispatchingTimedOut() ⭐  ← 注意方法名！                         │
│          ↓                                                                 │
│  AnrHelper.appNotResponding()                                              │
│          ↓                                                                 │
│  ProcessRecord.appNotResponding()                                          │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                        路径2: 应用主动上报ANR                                │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  应用进程（如卡顿监控库检测到主线程阻塞）                                       │
│          ↓                                                                 │
│  IActivityManager.appNotResponding(reason)  [Binder调用]                   │
│          ↓                                                                 │
│  ⭐ AMS.appNotResponding(String reason) ⭐  ← @Override 接口实现             │
│          ↓                                                                 │
│  AMS.appNotResponding(String reason, boolean isContinuousAnr)              │
│          ↓                                                                 │
│  AnrHelper.appNotResponding()                                              │
│          ↓                                                                 │
│  ProcessRecord.appNotResponding()                                          │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 六、其他 appNotResponding 重载方法

```java
// ========== 方法3: 内部调用（直接传ProcessRecord）==========
void appNotResponding(@NonNull ProcessRecord anrProcess, 
                      @NonNull TimeoutRecord timeoutRecord) {
    // 简单转发到AnrHelper
    // 被其他系统组件调用（如BroadcastQueue, ServiceTimeout等）
    mAnrHelper.appNotResponding(anrProcess, timeoutRecord);
}

// 使用场景：广播超时
// BroadcastQueue.java:
//     mService.appNotResponding(app, timeoutRecord);

// ========== 方法4: 通过进程名查找 ==========
private void appNotResponding(@NonNull String processName, 
                               int uid,
                               @NonNull TimeoutRecord timeoutRecord) {
    synchronized (this) {
        // 根据进程名和UID查找ProcessRecord
        final ProcessRecord app = getProcessRecordLocked(processName, uid);
        if (app == null) {
            Slog.e(TAG, "Unknown process: " + processName);
            return;
        }
        mAnrHelper.appNotResponding(app, timeoutRecord);
    }
}

// 使用场景：ContentProvider超时
// ContentProviderHelper.java:
//     mService.appNotResponding(cpr.name.getPackageName(), cpr.uid, timeoutRecord);
```

---

## 七、为什么AMS有这么多重载？

| 方法签名 | 调用者 | 用途 |
|---------|--------|------|
| `inputDispatchingTimedOut(pid, ...)` | AnrController | **输入ANR**专用入口 |
| `@Override appNotResponding(String)` | 应用进程（Binder） | 应用**主动上报**ANR |
| `appNotResponding(ProcessRecord, ...)` | BroadcastQueue, ActiveServices | **广播/服务ANR** |
| `appNotResponding(String, uid, ...)` | ContentProviderHelper | **ContentProvider ANR** |

**所有路径最终都汇聚到：**
```
AnrHelper.appNotResponding()
        ↓
ProcessRecord.appNotResponding()  // 真正执行dump、显示对话框等
```

---

## 八、回答用户问题

### Q: AMS复写 appNotResponding 干什么？

**A:** 这是实现 `IActivityManager.aidl` 接口，供应用进程通过Binder远程调用。当应用自己检测到卡顿时（如使用BlockCanary等库），可以主动调用此方法触发ANR。

### Q: 输入ANR会走到 @Override appNotResponding(String reason) 吗？

**A:** **不会！** 输入ANR走的是：
```
AnrController.notifyAnr()
        ↓
AMS.inputDispatchingTimedOut()  ← 走这个方法
        ↓
AnrHelper.appNotResponding()
```

`@Override appNotResponding(String reason)` 是给应用自己调用的。

### Q: 最后不是都走到AnrHelper吗？

**A:** **是的！** 无论哪条路径，最终都会走到：
```
AnrHelper.appNotResponding()
        ↓
ProcessRecord.appNotResponding()  // 统一的ANR处理逻辑
```

这是一种**收敛设计**：多个ANR触发点，统一的处理逻辑。
