# Android ANR 完整流程分析

## 概述

ANR (Application Not Responding) 机制是 Android 系统中用于检测应用无响应的重要机制。整个流程可以形象地比喻为"炸弹机制"：

- **埋炸弹**：设置一个延时消息（定时器），作为超时检测
- **拆炸弹**：在规定时间内完成任务，移除延时消息
- **引爆炸弹**：超时未完成，触发ANR

---

## 一、ANR 的类型和超时时间

| ANR 类型 | 超时时间 | 触发场景 |
|---------|---------|---------|
| Input ANR | 5秒 | 输入事件（按键、触摸）未在规定时间内处理完成 |
| Broadcast ANR | 前台10秒/后台60秒 | BroadcastReceiver 的 onReceive() 执行超时 |
| Service ANR | 前台20秒/后台200秒 | Service 的生命周期方法执行超时 |
| ContentProvider ANR | 10秒 | ContentProvider 发布超时 |

---

## 二、Input ANR 完整流程

### 2.1 整体流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Input ANR 流程                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   InputDispatcher                          App                           │
│        │                                    │                            │
│        │  ① 埋炸弹：记录 dispatchTime       │                            │
│        │  ─────────────────────────────────>│                            │
│        │     发送输入事件到应用               │                            │
│        │                                    │                            │
│        │                                    │ ② 处理事件                  │
│        │                                    │    (需要在5秒内完成)         │
│        │                                    │                            │
│        │  ③ 拆炸弹：收到 finishInputEvent    │                            │
│        │  <─────────────────────────────────│                            │
│        │     移除超时检测                    │                            │
│        │                                    │                            │
│   ─────┼────────────────────────────────────┼─────────────────────────   │
│        │                                    │                            │
│        │  ④ 引爆炸弹：超时未收到响应          │                            │
│        │     触发 ANR                       │                            │
│        │                                    │                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 埋炸弹（设置超时检测）

**位置**：`InputDispatcher::dispatchMotionLocked()` / `dispatchKeyLocked()`

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

InputEventInjectionResult InputDispatcher::dispatchMotionLocked(
        nsecs_t currentTime, std::shared_ptr<MotionEntry> entry,
        DropReason* dropReason, nsecs_t* nextWakeupTime) {
    
    // ... 省略其他代码 ...
    
    // 找到目标窗口
    std::vector<InputTarget> inputTargets;
    int32_t injectionResult = findTouchedWindowTargetsLocked(
            currentTime, *entry, inputTargets, nextWakeupTime, &conflictingPointerActions);
    
    // 分发事件到目标窗口
    dispatchEventLocked(currentTime, entry, inputTargets);
    
    return injectionResult;
}

void InputDispatcher::dispatchEventLocked(nsecs_t currentTime,
        std::shared_ptr<EventEntry> eventEntry,
        const std::vector<InputTarget>& inputTargets) {
    
    for (const InputTarget& inputTarget : inputTargets) {
        sp<Connection> connection = getConnectionLocked(inputTarget.inputChannel);
        if (connection != nullptr) {
            // 【埋炸弹】开始分发事件，记录分发时间
            prepareDispatchCycleLocked(currentTime, connection, eventEntry, inputTarget);
        }
    }
}

void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection) {
    
    while (connection->status == Connection::STATUS_NORMAL && !connection->outboundQueue.empty()) {
        DispatchEntry* dispatchEntry = connection->outboundQueue.front();
        
        // 【关键】记录事件发送时间 - 这就是"埋炸弹"
        dispatchEntry->deliveryTime = currentTime;
        
        // 发送事件到应用
        status_t status = connection->inputPublisher.publishMotionEvent(...);
        
        // 将事件从 outboundQueue 移到 waitQueue
        // waitQueue 中的事件等待应用响应
        connection->outboundQueue.erase(connection->outboundQueue.begin());
        connection->waitQueue.push_back(dispatchEntry);
    }
}
```

### 2.3 超时检测机制

```cpp
// InputDispatcher 周期性检查是否有超时事件

void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LONG_LONG_MAX;
    
    { // 加锁
        std::scoped_lock _l(mLock);
        
        // 检查是否有 ANR
        processAnrsLocked();
        
        // 分发待处理的事件
        dispatchOnceInnerLocked(&nextWakeupTime);
    }
    
    // 等待下一个事件或超时
    mLooper->pollOnce(timeoutMillis);
}

void InputDispatcher::processAnrsLocked() {
    nsecs_t currentTime = now();
    
    // 遍历所有连接，检查是否超时
    for (auto& [token, connection] : mConnectionsByToken) {
        // 检查 waitQueue 中的事件是否超时
        if (!connection->waitQueue.empty()) {
            DispatchEntry* dispatchEntry = connection->waitQueue.front();
            
            // 【关键】检查是否超时 - 超时时间为 5 秒
            nsecs_t waitDuration = currentTime - dispatchEntry->deliveryTime;
            if (waitDuration > DEFAULT_INPUT_DISPATCHING_TIMEOUT) {  // 5秒
                // 【引爆炸弹】发现超时，触发 ANR
                onAnrLocked(connection);
            }
        }
    }
}
```

### 2.4 拆炸弹（取消超时）

**位置**：应用处理完事件后，调用 `finishInputEvent()`

```cpp
// 应用端处理完成后的回调
// frameworks/base/core/java/android/view/ViewRootImpl.java

final class WindowInputEventReceiver extends InputEventReceiver {
    @Override
    public void onInputEvent(InputEvent event) {
        // 处理输入事件
        enqueueInputEvent(event, this, 0, true);
    }
}

void finishInputEvent(QueuedInputEvent q, boolean handled) {
    // 【拆炸弹】通知 InputDispatcher 事件处理完成
    if (q.mReceiver != null) {
        q.mReceiver.finishInputEvent(q.mEvent, handled);
    }
}
```

```cpp
// InputDispatcher 收到完成通知
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

void InputDispatcher::handleReceiveCallback(int events, sp<Connection> connection) {
    // 读取应用的响应
    bool handled = false;
    uint32_t seq;
    status_t status = connection->inputPublisher.receiveFinishedSignal(&seq, &handled);
    
    if (status == OK) {
        // 【拆炸弹】从 waitQueue 中移除已处理的事件
        finishDispatchCycleLocked(currentTime, connection, seq, handled);
    }
}

void InputDispatcher::finishDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection, uint32_t seq, bool handled) {
    
    // 在 waitQueue 中找到对应的事件
    for (auto it = connection->waitQueue.begin(); it != connection->waitQueue.end(); ) {
        DispatchEntry* dispatchEntry = *it;
        if (dispatchEntry->seq == seq) {
            // 【关键】移除事件，炸弹拆除成功
            it = connection->waitQueue.erase(it);
            delete dispatchEntry;
            return;
        }
    }
}
```

### 2.5 引爆炸弹（触发 ANR）

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

void InputDispatcher::onAnrLocked(const sp<Connection>& connection) {
    // 获取应用信息
    std::string reason = android::base::StringPrintf(
            "%s is not responding. Waited %dms for %s",
            connection->inputChannel->getName().c_str(),
            waitDuration / 1000000,
            eventDescription.c_str());
    
    // 通知 InputManagerService
    sp<IBinder> connectionToken = connection->inputChannel->getConnectionToken();
    mPolicy->notifyAnr(connection, reason);
}
```

```java
// frameworks/base/services/core/java/com/android/server/input/InputManagerService.java

private void notifyAnr(InputApplicationHandle inputApplicationHandle,
        IBinder token, String reason) {
    // 通知 ActivityManagerService
    mWindowManagerCallbacks.notifyAnr(inputApplicationHandle, token, reason);
}
```

---

## 三、Service ANR 完整流程

### 3.1 整体流程图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         Service ANR 流程                                    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   AMS                        ActiveServices                   App          │
│    │                              │                            │           │
│    │  startService()              │                            │           │
│    │─────────────────────────────>│                            │           │
│    │                              │                            │           │
│    │                              │ ① 埋炸弹                    │           │
│    │                              │ scheduleServiceTimeoutLocked│           │
│    │                              │ 发送 SERVICE_TIMEOUT_MSG    │           │
│    │                              │ (延时20秒/200秒)            │           │
│    │                              │                            │           │
│    │                              │ 启动 Service                │           │
│    │                              │───────────────────────────>│           │
│    │                              │                            │           │
│    │                              │                            │ onCreate  │
│    │                              │                            │ onStart   │
│    │                              │                            │           │
│    │                              │ ② 拆炸弹                    │           │
│    │                              │<───────────────────────────│           │
│    │                              │ serviceDoneExecutingLocked  │           │
│    │                              │ 移除 SERVICE_TIMEOUT_MSG    │           │
│    │                              │                            │           │
│   ─┼──────────────────────────────┼────────────────────────────┼───────────│
│    │                              │                            │           │
│    │                              │ ③ 引爆炸弹                  │           │
│    │                              │ 超时收到 SERVICE_TIMEOUT_MSG│           │
│    │                              │ 触发 ANR                    │           │
│    │                              │                            │           │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 埋炸弹

**位置**：`ActiveServices.scheduleServiceTimeoutLocked()`

```java
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java

void scheduleServiceTimeoutLocked(ProcessRecord proc) {
    if (proc.executingServices.size() == 0 || proc.thread == null) {
        return;
    }
    Message msg = mAm.mHandler.obtainMessage(
            ActivityManagerService.SERVICE_TIMEOUT_MSG);
    msg.obj = proc;
    
    // 【埋炸弹】发送延时消息
    // 前台服务: SERVICE_TIMEOUT = 20秒
    // 后台服务: SERVICE_BACKGROUND_TIMEOUT = 200秒
    mAm.mHandler.sendMessageDelayed(msg,
            proc.execServicesFg ? SERVICE_TIMEOUT : SERVICE_BACKGROUND_TIMEOUT);
}
```

**埋炸弹的调用时机**：

```java
// 1. 创建 Service 时
private String bringUpServiceLocked(ServiceRecord r, int intentFlags,
        boolean execInFg, boolean whileRestarting, boolean permissionsReviewRequired) {
    
    // 设置执行中标志
    bumpServiceExecutingLocked(r, execInFg, "create");
    
    // 启动 Service
    realStartServiceLocked(r, app, execInFg);
    
    return null;
}

private void bumpServiceExecutingLocked(ServiceRecord r, boolean fg, String why) {
    // ...
    
    // 【埋炸弹】
    scheduleServiceTimeoutLocked(r.app);
}

// 2. 绑定 Service 时
private boolean requestServiceBindingLocked(ServiceRecord r, IntentBindRecord i,
        boolean execInFg, boolean rebind) {
    
    // 【埋炸弹】
    bumpServiceExecutingLocked(r, execInFg, "bind");
    
    // 请求绑定
    r.app.thread.scheduleBindService(r, i.intent.getIntent(), rebind,
            r.app.getReportedProcState());
    
    return true;
}
```

### 3.3 拆炸弹

**位置**：`ActiveServices.serviceDoneExecutingLocked()`

```java
// Service 执行完成后调用
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java

private void serviceDoneExecutingLocked(ServiceRecord r, boolean inDestroying,
        boolean finishing) {
    
    r.executeNesting--;
    if (r.executeNesting <= 0) {
        if (r.app != null) {
            r.app.execServicesFg = false;
            r.app.executingServices.remove(r);
            
            if (r.app.executingServices.size() == 0) {
                // 【拆炸弹】移除超时消息
                mAm.mHandler.removeMessages(
                        ActivityManagerService.SERVICE_TIMEOUT_MSG, r.app);
            }
        }
    }
}
```

**拆炸弹的调用时机**：

```java
// 应用端完成 Service 生命周期方法后
// frameworks/base/core/java/android/app/ActivityThread.java

private void handleCreateService(CreateServiceData data) {
    // 创建 Service
    Service service = packageInfo.getAppFactory()
            .instantiateService(cl, data.info.name, data.intent);
    
    // 调用 onCreate
    service.onCreate();
    
    // 【拆炸弹】通知 AMS 创建完成
    ActivityManager.getService().serviceDoneExecuting(
            data.token, SERVICE_DONE_EXECUTING_ANON, 0, 0);
}
```

### 3.4 引爆炸弹

```java
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java

void serviceTimeout(ProcessRecord proc) {
    synchronized(mAm) {
        if (proc.executingServices.size() == 0 || proc.thread == null) {
            return;
        }
        
        // 检查是否真正超时
        final long now = SystemClock.uptimeMillis();
        final long maxTime = now - 
                (proc.execServicesFg ? SERVICE_TIMEOUT : SERVICE_BACKGROUND_TIMEOUT);
        
        ServiceRecord timeout = null;
        for (int i = proc.executingServices.size() - 1; i >= 0; i--) {
            ServiceRecord sr = proc.executingServices.valueAt(i);
            if (sr.executingStart < maxTime) {
                timeout = sr;
                break;
            }
        }
        
        if (timeout != null) {
            // 【引爆炸弹】触发 ANR
            mAm.mAnrHelper.appNotResponding(proc, 
                    "executing service " + timeout.shortInstanceName);
        }
    }
}
```

---

## 四、Broadcast ANR 完整流程

### 4.1 整体流程图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        Broadcast ANR 流程                                   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   AMS              BroadcastQueue                              App         │
│    │                    │                                       │          │
│    │ sendBroadcast()    │                                       │          │
│    │───────────────────>│                                       │          │
│    │                    │                                       │          │
│    │                    │ ① 埋炸弹                               │          │
│    │                    │ setBroadcastTimeoutLocked             │          │
│    │                    │ 发送 BROADCAST_TIMEOUT_MSG            │          │
│    │                    │ (前台10秒/后台60秒)                    │          │
│    │                    │                                       │          │
│    │                    │ 分发广播                               │          │
│    │                    │──────────────────────────────────────>│          │
│    │                    │                                       │          │
│    │                    │                                       │ onReceive│
│    │                    │                                       │          │
│    │                    │ ② 拆炸弹                               │          │
│    │                    │<──────────────────────────────────────│          │
│    │                    │ finishReceiverLocked                  │          │
│    │                    │ cancelBroadcastTimeoutLocked          │          │
│    │                    │                                       │          │
│   ─┼────────────────────┼───────────────────────────────────────┼──────────│
│    │                    │                                       │          │
│    │                    │ ③ 引爆炸弹                             │          │
│    │                    │ 超时收到 BROADCAST_TIMEOUT_MSG         │          │
│    │                    │ broadcastTimeoutLocked                │          │
│    │                    │ 触发 ANR                               │          │
│    │                    │                                       │          │
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 埋炸弹

**位置**：`BroadcastQueue.processNextBroadcastLocked()`

```java
// frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java

final void processNextBroadcastLocked(boolean fromMsg, boolean skipOomAdj) {
    BroadcastRecord r;
    
    // 处理有序广播
    do {
        r = mDispatcher.getNextBroadcastLocked(now);
        
        // ...
        
        // 【埋炸弹】设置广播超时
        // 前台广播: BROADCAST_FG_TIMEOUT = 10秒
        // 后台广播: BROADCAST_BG_TIMEOUT = 60秒
        long timeoutTime = r.receiverTime + mConstants.TIMEOUT;
        setBroadcastTimeoutLocked(timeoutTime);
        
        // 分发广播到接收者
        performReceiveLocked(r.app, r.receiver, ...);
        
    } while (r != null);
}

final void setBroadcastTimeoutLocked(long timeoutTime) {
    if (!mPendingBroadcastTimeoutMessage) {
        Message msg = mHandler.obtainMessage(BROADCAST_TIMEOUT_MSG, this);
        
        // 【埋炸弹】发送延时消息
        mHandler.sendMessageAtTime(msg, timeoutTime);
        mPendingBroadcastTimeoutMessage = true;
    }
}
```

### 4.3 拆炸弹

```java
// frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java

public boolean finishReceiverLocked(BroadcastRecord r, int resultCode,
        String resultData, Bundle resultExtras, boolean resultAbort, boolean waitForServices) {
    
    final int state = r.state;
    r.state = BroadcastRecord.IDLE;
    
    // 【拆炸弹】取消超时消息
    cancelBroadcastTimeoutLocked();
    
    // 处理下一个接收者
    // ...
    
    return state == BroadcastRecord.APP_RECEIVE;
}

final void cancelBroadcastTimeoutLocked() {
    if (mPendingBroadcastTimeoutMessage) {
        // 【拆炸弹】移除超时消息
        mHandler.removeMessages(BROADCAST_TIMEOUT_MSG, this);
        mPendingBroadcastTimeoutMessage = false;
    }
}
```

### 4.4 引爆炸弹

```java
// frameworks/base/services/core/java/com/android/server/am/BroadcastQueue.java

final void broadcastTimeoutLocked(boolean fromMsg) {
    if (fromMsg) {
        mPendingBroadcastTimeoutMessage = false;
    }
    
    if (mDispatcher.isEmpty()) {
        return;
    }
    
    long now = SystemClock.uptimeMillis();
    BroadcastRecord r = mDispatcher.getActiveBroadcastLocked();
    
    if (r != null) {
        // 检查是否真正超时
        long timeoutTime = r.receiverTime + mConstants.TIMEOUT;
        if (timeoutTime > now) {
            // 还没超时，重新设置超时
            setBroadcastTimeoutLocked(timeoutTime);
            return;
        }
    }
    
    // 【引爆炸弹】触发 ANR
    if (r.app != null) {
        mService.mAnrHelper.appNotResponding(r.app,
                "Broadcast of " + r.intent.toString());
    }
    
    // 跳过当前接收者，继续处理下一个
    finishReceiverLocked(r, r.resultCode, r.resultData,
            r.resultExtras, r.resultAbort, false);
    scheduleBroadcastsLocked();
}
```

---

## 五、ContentProvider ANR 完整流程

### 5.1 埋炸弹

```java
// frameworks/base/services/core/java/com/android/server/am/ContentProviderHelper.java

boolean publishContentProviders(IApplicationThread caller,
        List<ContentProviderHolder> providers) {
    
    // 启动应用进程时，会为 ContentProvider 发布设置超时
    // ...
}

// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

private boolean attachApplicationLocked(IApplicationThread thread,
        int pid, int callingUid, long startSeq) {
    
    // 【埋炸弹】发送超时消息
    // CONTENT_PROVIDER_PUBLISH_TIMEOUT = 10秒
    Message msg = mHandler.obtainMessage(CONTENT_PROVIDER_PUBLISH_TIMEOUT_MSG);
    msg.obj = r;
    mHandler.sendMessageDelayed(msg, CONTENT_PROVIDER_PUBLISH_TIMEOUT);
    
    return true;
}
```

### 5.2 拆炸弹

```java
// frameworks/base/services/core/java/com/android/server/am/ContentProviderHelper.java

void publishContentProviders(IApplicationThread caller,
        List<ContentProviderHolder> providers) {
    
    synchronized (mService) {
        // 发布 ContentProvider
        for (int i = 0; i < providers.size(); i++) {
            ContentProviderHolder src = providers.get(i);
            // ...
        }
        
        // 【拆炸弹】移除超时消息
        mService.mHandler.removeMessages(
                ActivityManagerService.CONTENT_PROVIDER_PUBLISH_TIMEOUT_MSG, r);
    }
}
```

### 5.3 引爆炸弹

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

case CONTENT_PROVIDER_PUBLISH_TIMEOUT_MSG: {
    ProcessRecord app = (ProcessRecord) msg.obj;
    synchronized (ActivityManagerService.this) {
        // 【引爆炸弹】
        processContentProviderPublishTimedOutLocked(app);
    }
}

private void processContentProviderPublishTimedOutLocked(ProcessRecord app) {
    // 清理未发布的 ContentProvider
    cleanupAppInLaunchingProvidersLocked(app, true);
    
    // 移除进程的死亡通知
    mProcessList.removeProcessLocked(app, false, true, 
            ApplicationExitInfo.REASON_INITIALIZATION_FAILURE,
            ApplicationExitInfo.SUBREASON_UNKNOWN,
            "timeout publishing content providers");
}
```

---

## 六、ANR 流程总结

### 6.1 三步曲模型

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ANR "炸弹"机制                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                 │
│  │              │     │              │     │              │                 │
│  │   埋炸弹      │────>│   拆炸弹     │  OR │   引爆炸弹    │                 │
│  │              │     │              │     │              │                 │
│  └──────────────┘     └──────────────┘     └──────────────┘                 │
│         │                   │                    │                          │
│         │                   │                    │                          │
│         ▼                   ▼                    ▼                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                 │
│  │ 发送延时消息  │     │ 移除延时消息  │     │ 触发 ANR     │                 │
│  │ 或记录时间戳  │     │ 标记完成      │     │ 收集日志     │                 │
│  └──────────────┘     └──────────────┘     │ 弹出对话框    │                 │
│                                            └──────────────┘                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 各类型 ANR 对比

| 类型 | 埋炸弹时机 | 埋炸弹方式 | 拆炸弹时机 | 引爆炸弹处理 |
|-----|----------|----------|----------|------------|
| Input | 分发事件时 | 记录 deliveryTime | 收到 finishInputEvent | onAnrLocked() |
| Service | 调用生命周期前 | 发送 SERVICE_TIMEOUT_MSG | 生命周期完成后 | serviceTimeout() |
| Broadcast | 分发广播前 | 发送 BROADCAST_TIMEOUT_MSG | onReceive() 完成后 | broadcastTimeoutLocked() |
| Provider | attach 应用时 | 发送 PROVIDER_PUBLISH_TIMEOUT_MSG | publish 完成后 | 直接杀进程 |

---

## 七、关键代码路径

### 7.1 Input ANR

```
InputDispatcher::dispatchEventLocked()
    └── startDispatchCycleLocked()           [埋炸弹]
        └── deliveryTime = currentTime

InputDispatcher::handleReceiveCallback()
    └── finishDispatchCycleLocked()          [拆炸弹]
        └── waitQueue.erase()

InputDispatcher::processAnrsLocked()
    └── onAnrLocked()                        [引爆炸弹]
```

### 7.2 Service ANR

```
ActiveServices::bringUpServiceLocked()
    └── bumpServiceExecutingLocked()
        └── scheduleServiceTimeoutLocked()   [埋炸弹]
            └── sendMessageDelayed(SERVICE_TIMEOUT_MSG)

ActivityThread::handleCreateService()
    └── ActivityManager.serviceDoneExecuting()
        └── serviceDoneExecutingLocked()     [拆炸弹]
            └── removeMessages(SERVICE_TIMEOUT_MSG)

MainHandler::handleMessage(SERVICE_TIMEOUT_MSG)
    └── serviceTimeout()                     [引爆炸弹]
        └── appNotResponding()
```

### 7.3 Broadcast ANR

```
BroadcastQueue::processNextBroadcastLocked()
    └── setBroadcastTimeoutLocked()          [埋炸弹]
        └── sendMessageAtTime(BROADCAST_TIMEOUT_MSG)

BroadcastQueue::finishReceiverLocked()
    └── cancelBroadcastTimeoutLocked()       [拆炸弹]
        └── removeMessages(BROADCAST_TIMEOUT_MSG)

BroadcastHandler::handleMessage(BROADCAST_TIMEOUT_MSG)
    └── broadcastTimeoutLocked()             [引爆炸弹]
        └── appNotResponding()
```

---

## 八、避免 ANR 的最佳实践

### 8.1 主线程耗时操作

```java
// ❌ 错误：在主线程执行耗时操作
public void onClick(View view) {
    // 网络请求、数据库操作等耗时任务
    loadDataFromNetwork();  // 可能导致 ANR
}

// ✅ 正确：使用异步处理
public void onClick(View view) {
    new Thread(() -> {
        loadDataFromNetwork();
        runOnUiThread(() -> updateUI());
    }).start();
}
```

### 8.2 BroadcastReceiver

```java
// ❌ 错误：在 onReceive 中执行耗时操作
@Override
public void onReceive(Context context, Intent intent) {
    // 耗时操作，可能导致 ANR
    processLargeData();
}

// ✅ 正确：启动 Service 处理耗时任务
@Override
public void onReceive(Context context, Intent intent) {
    Intent serviceIntent = new Intent(context, MyIntentService.class);
    context.startService(serviceIntent);
}
```

### 8.3 Service

```java
// ❌ 错误：在 Service 生命周期方法中执行耗时操作
@Override
public void onCreate() {
    super.onCreate();
    // 耗时初始化，可能导致 ANR
    initializeHeavyResources();
}

// ✅ 正确：异步初始化
@Override
public void onCreate() {
    super.onCreate();
    new Thread(this::initializeHeavyResources).start();
}
```

---

## 九、调试 ANR

### 9.1 ANR 日志位置

```bash
# ANR traces 文件
/data/anr/traces.txt

# 系统日志
adb logcat -b main -b system | grep -i anr
```

### 9.2 常用调试命令

```bash
# 查看 ANR traces
adb pull /data/anr/traces.txt

# 实时监控 ANR
adb logcat | grep "ANR in"

# 获取系统进程状态
adb shell dumpsys activity processes
```

---

## 参考资料

- Android 源码: [https://cs.android.com/](https://cs.android.com/)
- InputDispatcher: `frameworks/native/services/inputflinger/dispatcher/`
- ActiveServices: `frameworks/base/services/core/java/com/android/server/am/`
- BroadcastQueue: `frameworks/base/services/core/java/com/android/server/am/`
