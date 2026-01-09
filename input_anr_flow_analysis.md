# Android 输入ANR完整流程分析

## 概述

输入ANR（Application Not Responding）发生在应用程序未能在规定时间内处理输入事件时。Android系统的输入ANR超时时间默认为**5秒**。

## 核心类图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Native Layer                                 │
├─────────────────────────────────────────────────────────────────────┤
│  InputReader → InputDispatcher → InputChannel → App                  │
│       ↓              ↓                                               │
│  EventHub    AnrTracker/InputDispatcherThread                        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ (通过JNI)
┌─────────────────────────────────────────────────────────────────────┐
│                         Java Layer                                   │
├─────────────────────────────────────────────────────────────────────┤
│  InputManagerService → WindowManagerService → ActivityManagerService │
│                              ↓                                       │
│                    AnrController / ProcessRecord                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 第一部分：输入事件分发与超时检测（Native层）

### 1. InputDispatcher 核心类

**文件位置**: `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

```cpp
class InputDispatcher : public android::InputDispatcherInterface {
private:
    // ANR超时追踪器
    AnrTracker mAnrTracker;
    
    // 待处理的连接队列
    std::unordered_map<sp<IBinder>, sp<Connection>> mConnectionsByToken;
    
    // 分发线程
    sp<InputDispatcherThread> mDispatcherThread;
    
    // ANR超时时间常量
    static constexpr nsecs_t DEFAULT_INPUT_DISPATCHING_TIMEOUT = 5000 * 1000000LL; // 5秒
};
```

### 2. 事件分发入口

```cpp
// InputDispatcher.cpp
void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LONG_LONG_MAX;
    { // acquire lock
        std::scoped_lock _l(mLock);
        
        // 1. 处理命令队列
        if (!haveCommandsLocked()) {
            // 2. 分发待处理事件
            dispatchOnceInnerLocked(&nextWakeupTime);
        }
        
        // 3. 处理ANR检测
        processAnrsLocked();
    } // release lock
    
    // 4. 等待下一个事件或超时
    mLooper->pollOnce(timeoutMillis);
}
```

### 3. 按键/触摸事件分发

```cpp
// 分发按键事件
bool InputDispatcher::dispatchKeyLocked(nsecs_t currentTime, 
                                         std::shared_ptr<KeyEntry> entry,
                                         DropReason* dropReason, 
                                         nsecs_t* nextWakeupTime) {
    // 1. 找到目标窗口
    std::vector<InputTarget> inputTargets;
    int32_t injectionResult = findFocusedWindowTargetsLocked(currentTime, 
                                                              *entry, 
                                                              inputTargets, 
                                                              nextWakeupTime);
    
    if (injectionResult == INPUT_EVENT_INJECTION_PENDING) {
        // 2. 如果窗口繁忙，需要等待 - 这里可能触发ANR
        return false;
    }
    
    // 3. 分发到目标窗口
    dispatchEventLocked(currentTime, entry, inputTargets);
    return true;
}

// 分发触摸事件
bool InputDispatcher::dispatchMotionLocked(nsecs_t currentTime, 
                                            std::shared_ptr<MotionEntry> entry,
                                            DropReason* dropReason, 
                                            nsecs_t* nextWakeupTime) {
    // 类似逻辑...
    std::vector<InputTarget> inputTargets;
    int32_t injectionResult = findTouchedWindowTargetsLocked(currentTime, 
                                                               *entry, 
                                                               inputTargets, 
                                                               nextWakeupTime);
    // ...
}
```

### 4. 查找目标窗口（关键的ANR检测点）

```cpp
int32_t InputDispatcher::findFocusedWindowTargetsLocked(
        nsecs_t currentTime,
        const EventEntry& entry,
        std::vector<InputTarget>& inputTargets,
        nsecs_t* nextWakeupTime) {
    
    // 1. 获取当前焦点窗口
    sp<WindowInfoHandle> focusedWindowHandle = getFocusedWindowHandleLocked(displayId);
    
    // 2. 检查窗口是否准备好接收事件
    std::string reason;
    if (!checkWindowReadyForMoreInputLocked(currentTime, focusedWindowHandle, 
                                             entry, "focused", reason)) {
        // 3. 窗口未准备好 - 检查是否需要触发ANR
        const nsecs_t timeout = focusedWindowHandle->getDispatchingTimeout(
                                    DEFAULT_INPUT_DISPATCHING_TIMEOUT);
        
        if (currentTime >= entry.eventTime + timeout) {
            // 4. 超时！触发ANR
            onAnrLocked(focusedWindowHandle);
            return INPUT_EVENT_INJECTION_PENDING;
        }
        
        // 5. 未超时，继续等待
        *nextWakeupTime = entry.eventTime + timeout;
        return INPUT_EVENT_INJECTION_PENDING;
    }
    
    // 窗口准备好了，添加到目标列表
    addWindowTargetLocked(focusedWindowHandle, inputTargets);
    return INPUT_EVENT_INJECTION_SUCCEEDED;
}
```

### 5. 窗口就绪检查

```cpp
bool InputDispatcher::checkWindowReadyForMoreInputLocked(
        nsecs_t currentTime,
        const sp<WindowInfoHandle>& windowHandle,
        const EventEntry& eventEntry,
        const char* targetType,
        std::string& reason) {
    
    // 获取与窗口关联的连接
    sp<Connection> connection = getConnectionLocked(windowHandle->getToken());
    
    if (connection == nullptr) {
        reason = "窗口没有输入通道";
        return false;
    }
    
    // 检查连接状态
    if (connection->status != Connection::Status::NORMAL) {
        reason = "连接状态异常";
        return false;
    }
    
    // 关键检查：是否有待处理的事件未被应用确认
    if (connection->inputState.isOutOfSync()) {
        reason = "输入状态不同步";
        return false;
    }
    
    // 检查是否有等待响应的事件（重要！）
    if (eventEntry.type == EventEntry::Type::KEY) {
        // 按键事件：检查是否有未完成的按键事件
        if (connection->waitQueue.count() > 0 && 
            connection->waitQueue.front()->eventEntry->type == EventEntry::Type::KEY) {
            reason = "等待前一个按键事件完成";
            return false;
        }
    }
    
    // 检查触摸事件的等待队列
    if (eventEntry.type == EventEntry::Type::MOTION) {
        // 触摸事件可以积压，但有上限
        if (connection->waitQueue.count() >= MAX_QUEUED_MOTION_EVENTS) {
            reason = "触摸事件队列已满";
            return false;
        }
    }
    
    return true;
}
```

---

## 第二部分：ANR追踪器（AnrTracker）

### 6. AnrTracker 类

**文件位置**: `frameworks/native/services/inputflinger/dispatcher/AnrTracker.cpp`

```cpp
class AnrTracker {
public:
    // 添加ANR追踪条目
    void insert(nsecs_t timeoutTime, sp<IBinder> token);
    
    // 移除条目（事件被处理后）
    void erase(sp<IBinder> token);
    
    // 获取最早的超时时间
    std::optional<nsecs_t> firstTimeout() const;
    
    // 获取超时的token
    sp<IBinder> firstToken() const;
    
private:
    // 使用multiset按超时时间排序
    std::multiset<std::pair<nsecs_t, sp<IBinder>>> mAnrTimeouts;
};
```

### 7. 事件发送时添加ANR追踪

```cpp
void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
                                                 const sp<Connection>& connection) {
    while (!connection->outboundQueue.isEmpty()) {
        DispatchEntry* dispatchEntry = connection->outboundQueue.dequeue();
        
        // 1. 通过InputChannel发送事件到应用
        status_t status = connection->inputPublisher.publishKeyEvent(...);
        
        if (status == OK) {
            // 2. 将事件移到等待队列
            connection->waitQueue.enqueue(dispatchEntry);
            
            // 3. 添加ANR追踪 ⭐重要⭐
            nsecs_t timeout = dispatchEntry->timeoutTime;
            mAnrTracker.insert(timeout, connection->inputWindowHandle->getToken());
        }
    }
}
```

---

## 第三部分：ANR处理流程

### 8. processAnrsLocked - ANR处理入口

```cpp
void InputDispatcher::processAnrsLocked() {
    nsecs_t currentTime = now();
    
    // 1. 检查是否有超时的连接
    std::optional<nsecs_t> anrTime = mAnrTracker.firstTimeout();
    
    if (!anrTime.has_value() || *anrTime > currentTime) {
        return; // 没有超时
    }
    
    // 2. 获取超时的token
    sp<IBinder> token = mAnrTracker.firstToken();
    
    // 3. 查找对应的窗口
    sp<WindowInfoHandle> windowHandle = getWindowHandleLocked(token);
    
    if (windowHandle != nullptr) {
        // 4. 触发窗口ANR
        onAnrLocked(windowHandle);
    } else {
        // 5. 查找对应的应用（无焦点窗口的情况）
        std::shared_ptr<InputApplicationHandle> application = 
            getApplicationHandleLocked(token);
        if (application != nullptr) {
            onAnrLocked(application);
        }
    }
}
```

### 9. onAnrLocked - 触发ANR

```cpp
void InputDispatcher::onAnrLocked(const sp<WindowInfoHandle>& windowHandle) {
    // 1. 收集ANR信息
    std::string reason = android::base::StringPrintf(
        "Input dispatching timed out (%s)", 
        getAnrReasonLocked(windowHandle).c_str());
    
    // 2. 创建ANR命令
    std::unique_ptr<CommandEntry> commandEntry = 
        std::make_unique<CommandEntry>(&InputDispatcher::doNotifyAnrLockedInterruptible);
    
    commandEntry->inputWindowHandle = windowHandle;
    commandEntry->reason = reason;
    
    // 3. 将命令加入队列（稍后在锁外执行）
    postCommandLocked(std::move(commandEntry));
    
    // 4. 从ANR追踪器中移除
    mAnrTracker.erase(windowHandle->getToken());
}

void InputDispatcher::onAnrLocked(
        const std::shared_ptr<InputApplicationHandle>& application) {
    // 应用级ANR（没有焦点窗口时）
    std::unique_ptr<CommandEntry> commandEntry = 
        std::make_unique<CommandEntry>(&InputDispatcher::doNotifyNoFocusedWindowAnrLockedInterruptible);
    
    commandEntry->inputApplicationHandle = application;
    postCommandLocked(std::move(commandEntry));
}
```

### 10. 通知PolicyCallback（回调到Java层）

```cpp
// 窗口ANR通知
void InputDispatcher::doNotifyAnrLockedInterruptible(CommandEntry* commandEntry) {
    mLock.unlock();
    
    // 调用PolicyCallback（最终回调到Java层的InputManagerService）
    nsecs_t newTimeout = mPolicy->notifyAnr(commandEntry->inputApplicationHandle,
                                             commandEntry->inputWindowHandle,
                                             commandEntry->reason);
    
    mLock.lock();
    
    if (newTimeout > 0) {
        // 如果返回了新的超时时间，重新添加追踪
        // （给应用更多时间响应）
        resumeAfterAnr(commandEntry->inputWindowHandle->getToken(), newTimeout);
    }
}

// 无焦点窗口ANR通知
void InputDispatcher::doNotifyNoFocusedWindowAnrLockedInterruptible(
        CommandEntry* commandEntry) {
    mLock.unlock();
    
    mPolicy->notifyNoFocusedWindowAnr(commandEntry->inputApplicationHandle);
    
    mLock.lock();
}
```

---

## 第四部分：Java层ANR处理

### 11. InputManagerCallback（WMS中的回调）

**文件位置**: `frameworks/base/services/core/java/com/android/server/wm/InputManagerCallback.java`

```java
final class InputManagerCallback implements InputManagerService.WindowManagerCallbacks {
    
    private final WindowManagerService mService;
    
    /**
     * Native层通知窗口ANR
     */
    @Override
    public long notifyAnr(InputApplicationHandle appHandle,
                          InputWindowHandle windowHandle,
                          String reason) {
        
        final int windowPid;
        final boolean aboveSystem;
        final ActivityRecord activity;
        
        synchronized (mService.mGlobalLock) {
            // 1. 获取窗口信息
            WindowState windowState = windowHandle != null ? 
                (WindowState) windowHandle.windowState : null;
            
            if (windowState != null) {
                windowPid = windowState.mSession.mPid;
                activity = windowState.mActivityRecord;
                
                // 2. 检查窗口是否仍然存在
                if (!windowState.isVisible()) {
                    // 窗口已不可见，忽略ANR
                    return 0;
                }
            } else {
                windowPid = -1;
                activity = null;
            }
        }
        
        // 3. 调用ANR控制器处理
        return mService.mAnrController.notifyAnr(appHandle, windowHandle, 
                                                  windowPid, reason);
    }
    
    /**
     * Native层通知无焦点窗口ANR
     */
    @Override
    public void notifyNoFocusedWindowAnr(InputApplicationHandle appHandle) {
        // 应用没有焦点窗口但仍未处理事件
        mService.mAnrController.notifyNoFocusedWindowAnr(appHandle);
    }
}
```

### 12. AnrController 类

**文件位置**: `frameworks/base/services/core/java/com/android/server/wm/AnrController.java`

```java
class AnrController {
    
    private final WindowManagerService mService;
    private final ActivityManagerService mAms;
    
    /**
     * 处理窗口ANR
     */
    long notifyAnr(InputApplicationHandle appHandle,
                   InputWindowHandle windowHandle,
                   int windowPid,
                   String reason) {
        
        // 1. 获取进程信息
        final int pid = windowPid > 0 ? windowPid : getAppPid(appHandle);
        final boolean isBackground = isBackground(pid);
        
        // 2. 如果进程在后台，给予更多时间
        if (isBackground) {
            // 后台进程可能需要更多时间启动
            return 5000; // 返回5秒延迟
        }
        
        // 3. 收集诊断信息
        final File traceFile = collectTraces(pid, reason);
        
        // 4. 通知ActivityManagerService
        mAms.inputDispatchingTimedOut(pid, isAboveSystem(pid), reason);
        
        // 5. 返回0表示不再等待
        return 0;
    }
    
    /**
     * 收集ANR traces
     */
    private File collectTraces(int pid, String reason) {
        // 调用AMS收集traces
        return mAms.dumpStackTraces(pid, reason);
    }
}
```

### 13. ActivityManagerService.inputDispatchingTimedOut

**文件位置**: `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`

```java
public class ActivityManagerService extends IActivityManager.Stub {
    
    /**
     * 输入分发超时处理入口
     */
    public boolean inputDispatchingTimedOut(int pid, boolean aboveSystem, String reason) {
        ProcessRecord proc;
        
        synchronized (mProcLock) {
            // 1. 获取进程记录
            proc = mPidsSelfLocked.get(pid);
            
            if (proc == null) {
                Slog.w(TAG, "Input dispatching timed out for unknown pid: " + pid);
                return true; // 继续处理
            }
        }
        
        // 2. 调用带ProcessRecord的重载方法
        return inputDispatchingTimedOut(proc, null /* activityRecord */, 
                                        null /* parentActivity */,
                                        aboveSystem, reason);
    }
    
    /**
     * 核心ANR处理方法
     */
    public boolean inputDispatchingTimedOut(final ProcessRecord proc,
                                             final ActivityRecord activity,
                                             final ActivityRecord parent,
                                             final boolean aboveSystem,
                                             String reason) {
        
        // 1. 检查进程是否正在调试
        if (proc != null && proc.isDebugging()) {
            Slog.i(TAG, "Process is being debugged, ignoring ANR");
            return false; // 不处理ANR
        }
        
        // 2. 检查进程是否有instrumentation
        if (proc != null && proc.getActiveInstrumentation() != null) {
            Bundle info = new Bundle();
            info.putString("reason", reason);
            finishInstrumentationLocked(proc, Activity.RESULT_CANCELED, info);
            return true;
        }
        
        // 3. 触发ANR处理流程
        mAnrHelper.appNotResponding(proc, activity, parent, aboveSystem, reason);
        
        return true;
    }
}
```

### 14. AnrHelper 类

**文件位置**: `frameworks/base/services/core/java/com/android/server/am/AnrHelper.java`

```java
class AnrHelper {
    
    private final ActivityManagerService mService;
    private final AnrHandlerThread mAnrHandlerThread;
    
    /**
     * 应用无响应处理入口
     */
    void appNotResponding(ProcessRecord proc, ActivityRecord activity,
                          ActivityRecord parent, boolean aboveSystem,
                          String reason) {
        
        // 1. 创建ANR记录
        AnrRecord record = new AnrRecord(proc, activity, parent, 
                                          aboveSystem, reason,
                                          SystemClock.uptimeMillis());
        
        // 2. 加入ANR处理队列
        synchronized (mAnrRecords) {
            mAnrRecords.add(record);
        }
        
        // 3. 触发ANR处理线程
        mAnrHandlerThread.startAnr();
    }
    
    /**
     * ANR处理线程执行的方法
     */
    private void processAnr(AnrRecord record) {
        // 调用ProcessRecord的ANR处理
        record.proc.appNotResponding(record.activity, record.parent,
                                      record.aboveSystem, record.reason,
                                      record.isContinuous);
    }
}
```

### 15. ProcessRecord.appNotResponding - 核心ANR处理

**文件位置**: `frameworks/base/services/core/java/com/android/server/am/ProcessRecord.java`

```java
class ProcessRecord {
    
    /**
     * ANR核心处理方法
     */
    void appNotResponding(ActivityRecord activity, ActivityRecord parent,
                          boolean aboveSystem, String reason,
                          boolean isContinuous) {
        
        // 1. 更新ANR状态
        synchronized (mProcLock) {
            if (mAnrInfo != null && !isContinuous) {
                // 已经在处理ANR
                return;
            }
            mAnrInfo = new AnrInfo(reason, SystemClock.elapsedRealtime());
        }
        
        // 2. 记录事件到EventLog
        EventLog.writeEvent(EventLogTags.AM_ANR, 
                            mUserId, mPid, mProcessName, mInfo.flags, reason);
        
        // 3. 收集并dump堆栈信息
        final File tracesFile = ActivityManagerService.dumpStackTraces(
                firstPids,           // 主要进程列表（ANR进程优先）
                lastPids,            // 次要进程列表
                nativePids,          // native进程列表
                null,                // 额外进程
                tracesDir);
        
        // 4. 收集CPU使用信息
        updateCpuStatsNow();
        final ProcessCpuTracker cpuTracker = mService.mProcessCpuTracker;
        
        // 5. 构建ANR报告
        StringBuilder report = new StringBuilder();
        report.append("ANR in ").append(mProcessName);
        report.append(" (").append(mInfo.processName).append("/").append(mPid).append(")");
        report.append("\n");
        report.append("Reason: ").append(reason);
        report.append("\n");
        
        // 添加CPU使用信息
        if (cpuTracker != null) {
            report.append(cpuTracker.printCurrentLoad());
            report.append(cpuTracker.printCurrentState(anrTime));
        }
        
        // 6. 写入traces文件
        // 文件路径通常是: /data/anr/traces.txt
        
        // 7. 发送ANR广播
        makeAnrInfoFile(report.toString());
        
        // 8. 显示ANR对话框（如果需要）
        Message msg = mService.mUiHandler.obtainMessage(
                ActivityManagerService.SHOW_NOT_RESPONDING_UI_MSG);
        msg.obj = new AppNotRespondingDialog.Data(this, activity, aboveSystem);
        mService.mUiHandler.sendMessage(msg);
        
        // 9. 可能杀死进程
        if (isSilentAnr() || !isInterestingToUserLocked()) {
            // 后台ANR，直接杀死
            killProcess("background anr", ApplicationExitInfo.REASON_ANR, true);
        }
    }
}
```

---

## 第五部分：事件确认与ANR取消

### 16. 应用处理事件后的确认

**文件位置**: `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`

```cpp
/**
 * 应用通过InputChannel发回确认
 */
void InputDispatcher::handleReceiveCallback(int fd, int events, void* data) {
    sp<Connection> connection = static_cast<Connection*>(data);
    
    // 1. 读取应用的确认消息
    std::vector<InputMessage> messages;
    status_t status = connection->inputPublisher.receiveFinishedSignal(&messages);
    
    if (status != OK) {
        // 连接出错
        return;
    }
    
    { // acquire lock
        std::scoped_lock _l(mLock);
        
        for (const InputMessage& msg : messages) {
            // 2. 处理每个确认消息
            finishDispatchCycleLocked(now(), connection, msg.body.finished.seq,
                                       msg.body.finished.handled);
        }
    }
}

void InputDispatcher::finishDispatchCycleLocked(nsecs_t currentTime,
                                                  const sp<Connection>& connection,
                                                  uint32_t seq,
                                                  bool handled) {
    // 1. 从等待队列中移除已确认的事件
    DispatchEntry* dispatchEntry = connection->waitQueue.dequeue();
    
    if (dispatchEntry != nullptr) {
        // 2. 从ANR追踪器中移除 ⭐重要⭐
        // 这就是为什么及时处理事件能避免ANR
        mAnrTracker.erase(connection->inputWindowHandle->getToken());
        
        // 3. 释放资源
        delete dispatchEntry;
    }
}
```

---

## 第六部分：完整调用链路图

```
                                时间线
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [T+0ms] 输入事件产生                                                           │
│  EventHub::getEvents()                                                       │
│       │                                                                      │
│       ▼                                                                      │
│  InputReader::loopOnce()                                                     │
│       │                                                                      │
│       ▼                                                                      │
│  InputDispatcher::notifyKey() / notifyMotion()                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [T+0ms] 事件入队并开始分发                                                      │
│  InputDispatcher::dispatchOnce()                                             │
│       │                                                                      │
│       ├──► dispatchKeyLocked() / dispatchMotionLocked()                      │
│       │         │                                                            │
│       │         ├──► findFocusedWindowTargetsLocked()                        │
│       │         │         │                                                  │
│       │         │         └──► checkWindowReadyForMoreInputLocked()          │
│       │         │                                                            │
│       │         └──► dispatchEventLocked()                                   │
│       │                   │                                                  │
│       │                   └──► startDispatchCycleLocked()                    │
│       │                             │                                        │
│       │                             ├──► InputPublisher::publishKeyEvent()   │
│       │                             │    (通过InputChannel发送到应用)           │
│       │                             │                                        │
│       │                             └──► mAnrTracker.insert()                │
│       │                                  ⭐ 开始ANR计时 ⭐                      │
│       │                                                                      │
│       └──► processAnrsLocked()  ← 每次循环都检查                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
         [正常路径: 应用及时处理]          [ANR路径: 应用未响应]
                    │                           │
┌───────────────────┴────────────┐  ┌──────────┴────────────────────────────┐
│ [T+Xms, X < 5000]               │  │ [T+5000ms] ANR触发                      │
│                                 │  │                                        │
│ App处理事件                      │  │ processAnrsLocked()                    │
│      │                          │  │      │                                 │
│      ▼                          │  │      └──► mAnrTracker.firstTimeout()   │
│ InputConsumer::sendFinished()   │  │               检测到超时               │
│      │                          │  │                  │                     │
│      ▼                          │  │                  ▼                     │
│ InputDispatcher::               │  │ onAnrLocked(windowHandle)              │
│   handleReceiveCallback()       │  │      │                                 │
│      │                          │  │      ▼                                 │
│      ▼                          │  │ postCommandLocked(                     │
│ finishDispatchCycleLocked()     │  │   doNotifyAnrLockedInterruptible)      │
│      │                          │  │                                        │
│      ▼                          │  └────────────────────────────────────────┘
│ mAnrTracker.erase()             │                     │
│  ⭐ 取消ANR计时 ⭐                │                     ▼
│                                 │  ┌────────────────────────────────────────┐
│ [结束 - 无ANR]                   │  │ [Native→Java JNI调用]                   │
└─────────────────────────────────┘  │                                        │
                                     │ InputDispatcher::                      │
                                     │   doNotifyAnrLockedInterruptible()     │
                                     │      │                                 │
                                     │      ▼                                 │
                                     │ mPolicy->notifyAnr()                   │
                                     │  (NativeInputManager)                  │
                                     │      │                                 │
                                     │      ▼                                 │
                                     │ InputManagerService.notifyAnr()        │
                                     │  [JNI callback]                        │
                                     └────────────────────────────────────────┘
                                                        │
                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Java层ANR处理]                                                               │
│                                                                              │
│ InputManagerCallback.notifyAnr()                                             │
│      │  (WindowManagerService)                                               │
│      ▼                                                                       │
│ AnrController.notifyAnr()                                                    │
│      │                                                                       │
│      ▼                                                                       │
│ ActivityManagerService.inputDispatchingTimedOut()                            │
│      │                                                                       │
│      ▼                                                                       │
│ AnrHelper.appNotResponding()                                                 │
│      │                                                                       │
│      ▼                                                                       │
│ ProcessRecord.appNotResponding()                                             │
│      │                                                                       │
│      ├──► EventLog.writeEvent()           // 记录EventLog                    │
│      ├──► dumpStackTraces()               // dump堆栈到/data/anr/            │
│      ├──► ProcessCpuTracker               // 收集CPU信息                      │
│      ├──► makeAnrInfoFile()               // 生成ANR报告                      │
│      └──► SHOW_NOT_RESPONDING_UI_MSG      // 显示ANR对话框                    │
│                  │                                                           │
│                  ▼                                                           │
│      AppNotRespondingDialog.show()                                           │
│      (用户看到"应用无响应"对话框)                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第七部分：关键类和方法汇总

### Native层 (C++)

| 类名 | 文件位置 | 关键方法 |
|------|----------|----------|
| `InputDispatcher` | `InputDispatcher.cpp` | `dispatchOnce()`, `dispatchKeyLocked()`, `dispatchMotionLocked()`, `findFocusedWindowTargetsLocked()`, `startDispatchCycleLocked()`, `processAnrsLocked()`, `onAnrLocked()`, `finishDispatchCycleLocked()` |
| `AnrTracker` | `AnrTracker.cpp` | `insert()`, `erase()`, `firstTimeout()`, `firstToken()` |
| `Connection` | `Connection.h` | `waitQueue`, `outboundQueue`, `inputPublisher` |
| `InputPublisher` | `InputTransport.cpp` | `publishKeyEvent()`, `publishMotionEvent()`, `receiveFinishedSignal()` |
| `NativeInputManager` | `com_android_server_input_InputManagerService.cpp` | `notifyAnr()`, `notifyNoFocusedWindowAnr()` |

### Java层

| 类名 | 文件位置 | 关键方法 |
|------|----------|----------|
| `InputManagerService` | `InputManagerService.java` | `notifyAnr()` (native callback) |
| `InputManagerCallback` | `InputManagerCallback.java` | `notifyAnr()`, `notifyNoFocusedWindowAnr()` |
| `AnrController` | `AnrController.java` | `notifyAnr()`, `collectTraces()` |
| `WindowManagerService` | `WindowManagerService.java` | 持有`mAnrController` |
| `ActivityManagerService` | `ActivityManagerService.java` | `inputDispatchingTimedOut()`, `dumpStackTraces()` |
| `AnrHelper` | `AnrHelper.java` | `appNotResponding()`, `processAnr()` |
| `ProcessRecord` | `ProcessRecord.java` | `appNotResponding()` |
| `AppNotRespondingDialog` | `AppNotRespondingDialog.java` | ANR对话框UI |

---

## 第八部分：ANR类型与超时时间

| ANR类型 | 超时时间 | 触发场景 |
|---------|----------|----------|
| **Input ANR** | 5秒 | 按键/触摸事件未及时处理 |
| **Broadcast ANR** | 前台10秒/后台60秒 | 广播接收器超时 |
| **Service ANR** | 前台20秒/后台200秒 | Service启动超时 |
| **ContentProvider ANR** | 10秒 | ContentProvider发布超时 |

---

## 总结

输入ANR的完整流程可以概括为：

1. **事件产生**: `EventHub` → `InputReader` → `InputDispatcher`

2. **事件分发**: `InputDispatcher`通过`InputChannel`将事件发送到目标应用，同时在`AnrTracker`中记录超时时间

3. **超时检测**: `InputDispatcher`的分发循环不断调用`processAnrsLocked()`检查是否有超时

4. **ANR触发**: 若检测到超时，通过JNI回调到Java层

5. **ANR处理**: `InputManagerCallback` → `AnrController` → `ActivityManagerService` → `AnrHelper` → `ProcessRecord.appNotResponding()`

6. **信息收集**: dump堆栈、收集CPU信息、生成ANR报告

7. **用户通知**: 显示ANR对话框，用户可选择等待或关闭应用
