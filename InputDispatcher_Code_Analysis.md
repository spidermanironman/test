# InputDispatcher代码深入分析

## 文件位置

```
frameworks/native/services/inputflinger/dispatcher/
├── InputDispatcher.h
├── InputDispatcher.cpp
├── Connection.h
└── Connection.cpp
```

## 核心数据结构

### 1. EventEntry (事件条目)

```cpp
// frameworks/native/services/inputflinger/dispatcher/Entry.h
struct EventEntry {
    enum class Type {
        CONFIGURATION_CHANGED,
        DEVICE_RESET,
        KEY,
        MOTION,
        FOCUS,
        POINTER_CAPTURE_CHANGED,
        DRAG,
    };
    
    Type type;
    int32_t id;
    nsecs_t eventTime;      // 事件发生的时间
    uint32_t policyFlags;
    InjectionState* injectionState;
    
    EventEntry* prev;       // 双向链表
    EventEntry* next;
};

struct MotionEntry : EventEntry {
    nsecs_t eventTime;
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    uint32_t policyFlags;
    int32_t action;
    int32_t actionButton;
    int32_t flags;
    int32_t metaState;
    int32_t buttonState;
    MotionClassification classification;
    int32_t edgeFlags;
    float xPrecision;
    float yPrecision;
    float xCursorPosition;
    float yCursorPosition;
    nsecs_t downTime;
    uint32_t pointerCount;
    PointerProperties pointerProperties[MAX_POINTERS];
    PointerCoords pointerCoords[MAX_POINTERS];
};

struct KeyEntry : EventEntry {
    int32_t deviceId;
    uint32_t source;
    int32_t displayId;
    uint32_t policyFlags;
    int32_t action;
    int32_t flags;
    int32_t keyCode;
    int32_t scanCode;
    int32_t metaState;
    int32_t repeatCount;
    nsecs_t downTime;
};
```

### 2. Connection (连接)

```cpp
// frameworks/native/services/inputflinger/dispatcher/Connection.h
class Connection : public RefBase {
public:
    enum Status {
        STATUS_NORMAL,
        STATUS_BROKEN,
        STATUS_ZOMBIE,
        STATUS_NOT_RESPONDING,  // ANR状态
    };
    
    Status status;
    sp<InputChannel> inputChannel;
    sp<InputWindowHandle> inputWindowHandle;
    
    InputPublisher inputPublisher;  // 用于发送事件到应用
    
    // 三个关键队列的实际实现
    std::deque<DispatchEntry*> outboundQueue;  // 待发送队列
    std::deque<DispatchEntry*> waitQueue;       // 等待响应队列
    
    nsecs_t lastEventTime;    // 最后事件时间
    nsecs_t lastANRTime;      // 最后ANR时间
    
    // 用于查找waitQueue中的事件
    DispatchEntry* findWaitQueueEntry(uint32_t seq);
};
```

### 3. DispatchEntry (分发条目)

```cpp
struct DispatchEntry {
    const uint32_t seq;                      // 序列号，用于匹配finish响应
    sp<EventEntry> eventEntry;               // 关联的事件
    int32_t targetFlags;
    float xOffset;
    float yOffset;
    float globalScaleFactor;
    float windowXScale;
    float windowYScale;
    
    nsecs_t deliveryTime;     // 发送时间 - ANR计算的关键
    nsecs_t resolvedEventTime;
    uint32_t resolvedAction;
    int32_t resolvedFlags;
};
```

### 4. InputDispatcher主类

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.h
class InputDispatcher : public android::InputDispatcherInterface {
private:
    // Looper用于事件循环
    sp<Looper> mLooper;
    
    // 全局InboundQueue - 所有输入事件首先到达这里
    std::deque<EventEntry*> mInboundQueue;
    
    // 当前正在处理的事件
    EventEntry* mPendingEvent;
    
    // 所有的Connection映射 (token -> Connection)
    std::unordered_map<sp<IBinder>, sp<Connection>, IBinderHash> mConnectionsByToken;
    
    // 焦点窗口
    sp<InputWindowHandle> mFocusedWindowHandle;
    
    // ANR超时配置
    std::chrono::nanoseconds mNoFocusedWindowTimeout = 
        std::chrono::milliseconds(DEFAULT_INPUT_DISPATCHING_TIMEOUT);
    
    // 命令队列 - 用于延迟执行某些操作（如通知ANR）
    std::deque<CommandEntry*> mCommandQueue;
    
public:
    // 主要方法
    void dispatchOnce();                    // 主循环调用
    void notifyMotion(const NotifyMotionArgs* args);
    void notifyKey(const NotifyKeyArgs* args);
    
private:
    // 核心分发流程
    void dispatchOnceInnerLocked(nsecs_t* nextWakeupTime);
    void enqueueInboundEventLocked(EventEntry* entry);
    
    // 目标查找
    InputEventInjectionResult findFocusedWindowTargetsLocked(
            nsecs_t currentTime, const EventEntry& entry,
            std::vector<InputTarget>& inputTargets, nsecs_t* nextWakeupTime);
    
    InputEventInjectionResult findTouchedWindowTargetsLocked(
            nsecs_t currentTime, const MotionEntry& entry,
            std::vector<InputTarget>& inputTargets, nsecs_t* nextWakeupTime);
    
    // 事件分发
    void dispatchEventLocked(nsecs_t currentTime, EventEntry* eventEntry,
            const std::vector<InputTarget>& inputTargets);
    
    void prepareDispatchCycleLocked(nsecs_t currentTime,
            const sp<Connection>& connection,
            EventEntry* eventEntry, const InputTarget& inputTarget);
    
    void enqueueDispatchEntriesLocked(nsecs_t currentTime,
            const sp<Connection>& connection, EventEntry* eventEntry,
            const InputTarget& inputTarget);
    
    void startDispatchCycleLocked(nsecs_t currentTime,
            const sp<Connection>& connection);
    
    void finishDispatchCycleLocked(nsecs_t currentTime,
            const sp<Connection>& connection, uint32_t seq, bool handled);
    
    // ANR相关
    void onANRLocked(nsecs_t currentTime, const sp<Application>& application,
            const sp<InputWindowHandle>& windowHandle,
            const sp<IBinder>& token, nsecs_t eventTime,
            nsecs_t waitStartTime, const char* reason);
    
    nsecs_t getTimeoutExtensionLocked(const sp<InputWindowHandle>& windowHandle);
    
    bool checkWindowReadyForMoreInputLocked(nsecs_t currentTime,
            const sp<Connection>& connection,
            const EventEntry& eventEntry, const char* targetType);
};
```

## 详细代码流程

### 1. 事件入队 (notifyMotion)

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

void InputDispatcher::notifyMotion(const NotifyMotionArgs* args) {
    ALOGD_IF(DEBUG_INBOUND_EVENT_DETAILS,
             "notifyMotion - eventTime=%" PRId64 ", deviceId=%d, source=%s, "
             "displayId=%d, action=%s, actionButton=0x%08x, flags=0x%08x, "
             "metaState=0x%08x, buttonState=0x%08x, "
             "edgeFlags=0x%08x, pointerCount=%d",
             args->eventTime, args->deviceId, inputEventSourceToString(args->source).c_str(),
             args->displayId, motionActionToString(args->action).c_str(),
             args->actionButton, args->flags, args->metaState, args->buttonState,
             args->edgeFlags, args->pointerCount);

    // 创建MotionEntry
    MotionEntry* newEntry = new MotionEntry(
            args->id, args->eventTime, args->deviceId, args->source, args->displayId,
            args->policyFlags, args->action, args->actionButton, args->flags,
            args->metaState, args->buttonState, args->classification,
            args->edgeFlags, args->xPrecision, args->yPrecision,
            args->xCursorPosition, args->yCursorPosition,
            args->downTime, args->pointerCount, args->pointerProperties,
            args->pointerCoords);

    // 策略预处理（可能会修改事件或丢弃）
    bool needWake = false;
    {
        std::scoped_lock _l(mLock);
        
        // 应用策略拦截
        bool drop = false;
        if (mPolicy->filterInputEvent(newEntry, args->policyFlags)) {
            drop = true;
        }
        
        if (!drop) {
            // 加入InboundQueue
            needWake = enqueueInboundEventLocked(newEntry);
        } else {
            // 策略决定丢弃事件
            ALOGD("Dropping event due to policy");
            delete newEntry;
        }
    }
    
    // 唤醒InputDispatcher线程
    if (needWake) {
        mLooper->wake();
    }
}

bool InputDispatcher::enqueueInboundEventLocked(EventEntry* entry) {
    bool needWake = mInboundQueue.empty();
    
    // 添加到队列尾部
    mInboundQueue.push_back(entry);
    
    // 记录追踪信息
    traceInboundQueueLengthLocked();
    
    // 如果队列之前为空，需要唤醒Dispatcher线程
    return needWake;
}
```

### 2. 主分发循环 (dispatchOnce)

```cpp
void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LONG_LONG_MAX;
    {
        std::scoped_lock _l(mLock);
        
        // 处理命令队列中的命令（如ANR通知）
        mDispatcherIsAlive.notify_all();
        if (!haveCommandsLocked()) {
            dispatchOnceInnerLocked(&nextWakeupTime);
        }
        
        // 执行命令队列中的所有命令
        if (runCommandsLockedInterruptible()) {
            nextWakeupTime = LONG_LONG_MIN;
        }
        
        // 检查是否需要处理超时的连接
        nsecs_t currentTime = now();
        int timeoutMillis = toMillisecondTimeoutDelay(currentTime, nextWakeupTime);
        
    } // release lock
    
    // 等待新事件或超时
    mLooper->pollOnce(timeoutMillis);
}

void InputDispatcher::dispatchOnceInnerLocked(nsecs_t* nextWakeupTime) {
    nsecs_t currentTime = now();
    
    // 如果没有待处理事件，从InboundQueue获取
    if (!mPendingEvent) {
        if (mInboundQueue.empty()) {
            // 没有事件，空闲状态
            if (!mPendingEvent) {
                return;
            }
        } else {
            // 从InboundQueue取出第一个事件
            mPendingEvent = mInboundQueue.front();
            mInboundQueue.pop_front();
            traceInboundQueueLengthLocked();
        }
        
        // 重置ANR状态
        resetANRTimeoutsLocked();
    }
    
    // 根据事件类型进行分发
    bool done = false;
    DropReason dropReason = DropReason::NOT_DROPPED;
    
    switch (mPendingEvent->type) {
        case EventEntry::Type::CONFIGURATION_CHANGED: {
            // 配置改变
            done = dispatchConfigurationChangedLocked(currentTime, 
                    static_cast<ConfigurationChangedEntry*>(mPendingEvent));
            dropReason = DropReason::NOT_DROPPED;
            break;
        }
        
        case EventEntry::Type::KEY: {
            KeyEntry* keyEntry = static_cast<KeyEntry*>(mPendingEvent);
            
            // 查找焦点窗口
            std::vector<InputTarget> inputTargets;
            InputEventInjectionResult injectionResult =
                    findFocusedWindowTargetsLocked(currentTime, *keyEntry, inputTargets,
                                                   nextWakeupTime);
            
            if (injectionResult == InputEventInjectionResult::SUCCEEDED) {
                // 分发到目标窗口
                dispatchEventLocked(currentTime, mPendingEvent, inputTargets);
            }
            
            done = true;
            break;
        }
        
        case EventEntry::Type::MOTION: {
            MotionEntry* motionEntry = static_cast<MotionEntry*>(mPendingEvent);
            
            // 查找触摸目标窗口
            std::vector<InputTarget> inputTargets;
            InputEventInjectionResult injectionResult =
                    findTouchedWindowTargetsLocked(currentTime, *motionEntry, inputTargets,
                                                   nextWakeupTime);
            
            if (injectionResult == InputEventInjectionResult::SUCCEEDED) {
                // 分发到目标窗口
                dispatchEventLocked(currentTime, mPendingEvent, inputTargets);
            }
            
            done = true;
            break;
        }
        
        // ... 其他事件类型
    }
    
    if (done) {
        // 事件已处理完成，释放并清空mPendingEvent
        releasePendingEventLocked();
        *nextWakeupTime = LONG_LONG_MIN; // 立即处理下一个事件
    }
}
```

### 3. 查找焦点窗口 (findFocusedWindowTargetsLocked) - **ANR检测点**

```cpp
InputEventInjectionResult InputDispatcher::findFocusedWindowTargetsLocked(
        nsecs_t currentTime, const EventEntry& entry,
        std::vector<InputTarget>& inputTargets, nsecs_t* nextWakeupTime) {
    
    InputEventInjectionResult injectionResult = InputEventInjectionResult::FAILED;
    std::string reason;
    
    // 获取焦点窗口
    sp<InputWindowHandle> focusedWindowHandle = getFocusedWindowLocked(entry.displayId);
    sp<InputApplicationHandle> focusedApplicationHandle =
            getValueByKey(mFocusedApplicationHandlesByDisplay, entry.displayId);
    
    // 如果没有焦点窗口
    if (focusedWindowHandle == nullptr) {
        if (focusedApplicationHandle != nullptr) {
            // 有焦点应用但没有焦点窗口，可能正在启动
            // 检查是否超时
            nsecs_t timeout = mNoFocusedWindowTimeout;
            nsecs_t timeoutTime = entry.eventTime + timeout;
            if (currentTime < timeoutTime) {
                // 还在超时时间内，等待
                *nextWakeupTime = timeoutTime;
                return InputEventInjectionResult::PENDING;
            }
            
            // 超时，触发ANR
            onANRLocked(currentTime, focusedApplicationHandle,
                       nullptr /*windowHandle*/, entry.id, entry.eventTime,
                       entry.eventTime, "No focused window");
        }
        return InputEventInjectionResult::FAILED;
    }
    
    // 检查焦点窗口是否准备接收输入 - **关键ANR检测**
    if (!checkWindowReadyForMoreInputLocked(currentTime,
                                           focusedWindowHandle->getConnection(),
                                           entry, "focused")) {
        // 窗口未准备好（可能ANR）
        return InputEventInjectionResult::PENDING;
    }
    
    // 添加到目标列表
    injectionResult = InputEventInjectionResult::SUCCEEDED;
    addWindowTargetLocked(focusedWindowHandle,
                         InputTarget::FLAG_FOREGROUND | InputTarget::FLAG_DISPATCH_AS_IS,
                         BitSet32(0), inputTargets);
    
    return injectionResult;
}

// **核心ANR检测函数**
bool InputDispatcher::checkWindowReadyForMoreInputLocked(
        nsecs_t currentTime, const sp<Connection>& connection,
        const EventEntry& eventEntry, const char* targetType) {
    
    // 检查连接状态
    if (connection->status != Connection::STATUS_NORMAL) {
        ALOGD("Channel '%s' is %s. Dropping event.",
              connection->getInputChannelName().c_str(),
              connection->status == Connection::STATUS_BROKEN ? "broken" : "zombie");
        return false;
    }
    
    // **检查WaitQueue是否已满**
    if (connection->waitQueue.size() >= MAX_QUEUED_EVENTS) {
        ALOGE("Channel '%s' has too many events waiting (%zu). "
              "Dropping event.",
              connection->getInputChannelName().c_str(),
              connection->waitQueue.size());
        return false;
    }
    
    // **检查WaitQueue中最旧事件的等待时间**
    if (!connection->waitQueue.empty()) {
        DispatchEntry* oldestEntry = connection->waitQueue.front();
        
        // 计算等待时长
        nsecs_t waitDuration = currentTime - oldestEntry->deliveryTime;
        
        // 获取超时时间（可能有扩展）
        nsecs_t timeout = getDispatchingTimeoutLocked(connection);
        
        if (waitDuration >= timeout) {
            // **触发ANR！**
            ALOGE("Channel '%s' is not responding. "
                  "Waited %" PRId64 "ms for %s event",
                  connection->getInputChannelName().c_str(),
                  ns2ms(waitDuration), EventEntry::typeToString(oldestEntry->eventEntry->type));
            
            // 标记连接为NOT_RESPONDING
            connection->status = Connection::STATUS_NOT_RESPONDING;
            
            // 触发ANR回调
            sp<InputWindowHandle> windowHandle = connection->inputWindowHandle;
            if (windowHandle != nullptr) {
                onANRLocked(currentTime, windowHandle->getApplicationToken(),
                           windowHandle, eventEntry.id, eventEntry.eventTime,
                           oldestEntry->deliveryTime,
                           "Application is not responding");
            }
            
            return false;
        } else {
            // 还未超时，更新下次唤醒时间
            nsecs_t nextTimeout = oldestEntry->deliveryTime + timeout;
            if (nextTimeout < *nextWakeupTime) {
                *nextWakeupTime = nextTimeout;
            }
        }
    }
    
    return true;
}
```

### 4. 分发事件到目标 (dispatchEventLocked)

```cpp
void InputDispatcher::dispatchEventLocked(nsecs_t currentTime,
        EventEntry* eventEntry, const std::vector<InputTarget>& inputTargets) {
    
    // 记录追踪信息
    ALOGD_IF(DEBUG_DISPATCH_CYCLE,
             "dispatchEventLocked - eventTime=%" PRId64 ", targets.size=%zu",
             eventEntry->eventTime, inputTargets.size());
    
    // 为每个目标窗口准备分发循环
    for (const InputTarget& inputTarget : inputTargets) {
        sp<Connection> connection = getConnectionLocked(inputTarget.inputChannel->getConnectionToken());
        
        if (connection != nullptr) {
            prepareDispatchCycleLocked(currentTime, connection, eventEntry, inputTarget);
        } else {
            ALOGW("Dropping event delivery to target with channel '%s' "
                  "because we can't find the connection.",
                  inputTarget.inputChannel->getName().c_str());
        }
    }
}

void InputDispatcher::prepareDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection,
        EventEntry* eventEntry, const InputTarget& inputTarget) {
    
    ALOGD_IF(DEBUG_DISPATCH_CYCLE,
             "channel '%s' ~ prepareDispatchCycle - flags=0x%08x",
             connection->getInputChannelName().c_str(), inputTarget.flags);
    
    // 检查连接是否正常
    if (connection->status != Connection::STATUS_NORMAL) {
        ALOGD("channel '%s' ~ Dropping event because the channel status is %s",
              connection->getInputChannelName().c_str(),
              connection->getStatusLabel());
        return;
    }
    
    // 根据事件类型准备分发条目
    enqueueDispatchEntriesLocked(currentTime, connection, eventEntry, inputTarget);
}

void InputDispatcher::enqueueDispatchEntriesLocked(nsecs_t currentTime,
        const sp<Connection>& connection,
        EventEntry* eventEntry, const InputTarget& inputTarget) {
    
    bool wasEmpty = connection->outboundQueue.empty();
    
    // 创建DispatchEntry
    DispatchEntry* dispatchEntry = createDispatchEntry(inputTarget, eventEntry,
                                                       inputTarget.flags);
    
    // **加入OutboundQueue**
    connection->outboundQueue.push_back(dispatchEntry);
    traceOutboundQueueLength(connection);
    
    // 如果之前队列为空，立即开始发送
    if (wasEmpty && !connection->outboundQueue.empty()) {
        startDispatchCycleLocked(currentTime, connection);
    }
}
```

### 5. 发送事件 (startDispatchCycleLocked) - OutboundQueue → WaitQueue

```cpp
void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection) {
    
    ALOGD_IF(DEBUG_DISPATCH_CYCLE,
             "channel '%s' ~ startDispatchCycle",
             connection->getInputChannelName().c_str());
    
    // 循环发送OutboundQueue中的所有事件
    while (!connection->outboundQueue.empty()) {
        DispatchEntry* dispatchEntry = connection->outboundQueue.front();
        dispatchEntry->deliveryTime = currentTime; // **记录发送时间 - ANR计算关键**
        
        const std::chrono::nanoseconds timeout = getDispatchingTimeoutLocked(connection);
        dispatchEntry->timeoutTime = currentTime + timeout.count();
        
        // 通过InputPublisher发送事件
        status_t status;
        const EventEntry& eventEntry = *(dispatchEntry->eventEntry);
        
        switch (eventEntry.type) {
            case EventEntry::Type::KEY: {
                const KeyEntry& keyEntry = static_cast<const KeyEntry&>(eventEntry);
                std::array<uint8_t, 32> hmac = getSignature(keyEntry, *dispatchEntry);
                
                // 发布按键事件
                status = connection->inputPublisher.publishKeyEvent(
                        dispatchEntry->seq,
                        keyEntry.id,
                        keyEntry.deviceId,
                        keyEntry.source,
                        keyEntry.displayId,
                        std::move(hmac),
                        dispatchEntry->resolvedAction,
                        dispatchEntry->resolvedFlags,
                        keyEntry.keyCode,
                        keyEntry.scanCode,
                        keyEntry.metaState,
                        keyEntry.repeatCount,
                        keyEntry.downTime,
                        keyEntry.eventTime);
                break;
            }
            
            case EventEntry::Type::MOTION: {
                const MotionEntry& motionEntry = static_cast<const MotionEntry&>(eventEntry);
                
                // 发布触摸事件
                status = connection->inputPublisher.publishMotionEvent(
                        dispatchEntry->seq,
                        motionEntry.id,
                        motionEntry.deviceId,
                        motionEntry.source,
                        motionEntry.displayId,
                        std::move(hmac),
                        dispatchEntry->resolvedAction,
                        dispatchEntry->resolvedFlags,
                        motionEntry.edgeFlags,
                        motionEntry.metaState,
                        motionEntry.buttonState,
                        motionEntry.classification,
                        dispatchEntry->xOffset,
                        dispatchEntry->yOffset,
                        motionEntry.xPrecision,
                        motionEntry.yPrecision,
                        motionEntry.xCursorPosition,
                        motionEntry.yCursorPosition,
                        motionEntry.downTime,
                        motionEntry.eventTime,
                        motionEntry.pointerCount,
                        motionEntry.pointerProperties,
                        usingCoords);
                break;
            }
            
            // ... 其他事件类型
        }
        
        if (status != OK) {
            // 发送失败
            ALOGE("channel '%s' ~ Could not publish event. status=%d",
                  connection->getInputChannelName().c_str(), status);
            abortBrokenDispatchCycleLocked(currentTime, connection, true /*notify*/);
            return;
        }
        
        // **从OutboundQueue移到WaitQueue**
        connection->outboundQueue.erase(connection->outboundQueue.begin());
        traceOutboundQueueLength(connection);
        
        connection->waitQueue.push_back(dispatchEntry);
        traceWaitQueueLength(connection);
        
        ALOGD_IF(DEBUG_DISPATCH_CYCLE,
                 "channel '%s' ~ Sent event. seq=%u, waitQueue.size=%zu",
                 connection->getInputChannelName().c_str(),
                 dispatchEntry->seq,
                 connection->waitQueue.size());
    }
}
```

### 6. 接收完成响应 (finishDispatchCycleLocked) - 从WaitQueue移除

```cpp
// Looper回调，当Socket有数据可读时调用
int InputDispatcher::handleReceiveCallback(int fd, int events, void* data) {
    Connection* connection = static_cast<Connection*>(data);
    
    bool notify;
    {
        std::scoped_lock _l(mLock);
        
        // 接收应用发送的finish信号
        uint32_t seq;
        bool handled;
        status_t status = connection->inputPublisher.receiveFinishedSignal(&seq, &handled);
        
        if (status != OK) {
            ALOGE("channel '%s' ~ Failed to receive finished signal. status=%d",
                  connection->getInputChannelName().c_str(), status);
            notify = true;
        } else {
            ALOGD_IF(DEBUG_TRANSPORT,
                     "channel '%s' ~ Received finished signal. seq=%u, handled=%s",
                     connection->getInputChannelName().c_str(), seq, toString(handled));
            
            // 完成分发循环
            nsecs_t currentTime = now();
            finishDispatchCycleLocked(currentTime, connection, seq, handled);
            notify = false;
        }
    }
    
    if (notify) {
        // 通知连接断开
        onDispatchCycleFinishedLocked(currentTime, connection, seq, handled);
    }
    
    return 1; // keep callback registered
}

void InputDispatcher::finishDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection, uint32_t seq, bool handled) {
    
    ALOGD_IF(DEBUG_DISPATCH_CYCLE,
             "channel '%s' ~ finishDispatchCycle - seq=%u, handled=%s",
             connection->getInputChannelName().c_str(), seq, toString(handled));
    
    // **从WaitQueue中查找并移除对应的DispatchEntry**
    DispatchEntry* dispatchEntry = connection->findWaitQueueEntry(seq);
    if (dispatchEntry == nullptr) {
        ALOGW("channel '%s' ~ Received finish signal for unknown sequence number %u",
              connection->getInputChannelName().c_str(), seq);
        return;
    }
    
    // 计算处理时长
    nsecs_t processingTime = currentTime - dispatchEntry->deliveryTime;
    ALOGD_IF(DEBUG_DISPATCH_CYCLE,
             "channel '%s' ~ Event processing time: %" PRId64 "ms",
             connection->getInputChannelName().c_str(), ns2ms(processingTime));
    
    // **从WaitQueue移除**
    connection->waitQueue.erase(
            std::find(connection->waitQueue.begin(), connection->waitQueue.end(), dispatchEntry));
    traceWaitQueueLength(connection);
    
    // 如果窗口之前是NOT_RESPONDING状态，现在恢复了
    if (connection->status == Connection::STATUS_NOT_RESPONDING) {
        connection->status = Connection::STATUS_NORMAL;
        ALOGI("channel '%s' ~ Channel is no longer unresponsive",
              connection->getInputChannelName().c_str());
    }
    
    // 释放DispatchEntry
    delete dispatchEntry;
    
    // 继续处理outboundQueue中剩余的事件
    if (!connection->outboundQueue.empty()) {
        startDispatchCycleLocked(currentTime, connection);
    }
}
```

### 7. ANR触发 (onANRLocked)

```cpp
void InputDispatcher::onANRLocked(nsecs_t currentTime,
        const sp<IBinder>& applicationToken,
        const sp<InputWindowHandle>& windowHandle,
        int32_t eventId, nsecs_t eventTime,
        nsecs_t waitStartTime, const char* reason) {
    
    float dispatchLatency = (currentTime - waitStartTime) * 0.000001f; // 转换为毫秒
    
    ALOGI("ANR detected! "
          "Application token: %p, Window: %s, "
          "Wait duration: %.1fms, Reason: %s",
          applicationToken.get(),
          windowHandle != nullptr ? windowHandle->getName().c_str() : "<null>",
          dispatchLatency,
          reason);
    
    // 收集诊断信息
    std::string windowLabel;
    if (windowHandle != nullptr) {
        windowLabel = windowHandle->getName();
        
        // 获取Connection信息
        sp<Connection> connection = getConnectionLocked(windowHandle->getToken());
        if (connection != nullptr) {
            ALOGI("ANR - WaitQueue size: %zu, OutboundQueue size: %zu",
                  connection->waitQueue.size(),
                  connection->outboundQueue.size());
            
            // 打印WaitQueue中的事件详情
            for (DispatchEntry* entry : connection->waitQueue) {
                nsecs_t age = currentTime - entry->deliveryTime;
                ALOGI("  WaitQueue entry: seq=%u, age=%.1fms, type=%s",
                      entry->seq,
                      age * 0.000001f,
                      EventEntry::typeToString(entry->eventEntry->type));
            }
        }
    }
    
    // 创建ANR命令，稍后异步通知AMS
    std::unique_ptr<CommandEntry> commandEntry =
            std::make_unique<CommandEntry>(&InputDispatcher::doNotifyANRLockedInterruptible);
    commandEntry->applicationToken = applicationToken;
    commandEntry->windowHandle = windowHandle;
    commandEntry->reason = reason;
    commandEntry->eventTime = eventTime;
    commandEntry->waitStartTime = waitStartTime;
    
    mCommandQueue.push_back(std::move(commandEntry));
}

void InputDispatcher::doNotifyANRLockedInterruptible(CommandEntry* commandEntry) {
    // 解锁以避免死锁（AMS可能会回调InputDispatcher）
    mLock.unlock();
    
    // 调用InputDispatcherPolicy通知ANR
    // 这会调用到InputManagerService，最终到ActivityManagerService
    nsecs_t newTimeout = mPolicy->notifyANR(
            commandEntry->applicationToken,
            commandEntry->windowHandle,
            commandEntry->reason);
    
    // 重新加锁
    mLock.lock();
    
    // 如果AMS返回了新的超时时间（如用户选择"等待"），更新超时
    if (newTimeout > 0) {
        resumeAfterTargetsNotReadyTimeoutLocked(newTimeout,
                                               commandEntry->windowHandle);
    }
}
```

## 队列状态转换图

```
事件生命周期完整视图：

T0: 事件产生 (硬件 → InputReader)
    |
    v
T1: EventEntry创建
    |
    v
┌─────────────────┐
│  InboundQueue   │ ← notifyMotion/notifyKey
│   [Event1]      │
│   [Event2]      │
│   [Event3]      │
└────────┬────────┘
         │ dispatchOnceInnerLocked()
         │ - 取出Event1
         │ - findFocusedWindow / findTouchedWindow
         │ - **检查目标Window的WaitQueue (ANR检测)**
         │
         v
T2: 查找目标窗口
    |
    v
Connection (每个窗口)
    |
    v
┌──────────────────┐
│  OutboundQueue   │ ← enqueueDispatchEntriesLocked
│   [Event1]       │
└────────┬─────────┘
         │ startDispatchCycleLocked()
         │ - 通过Socket发送
         │ - 记录deliveryTime (ANR计算基准)
         │
         v
T3: 事件发送
    |
    v
┌──────────────────┐
│   WaitQueue      │ ← 等待应用finishInputEvent
│   [Event1] T=0   │   **ANR监控队列**
│   [Event2] T=1   │
│   [Event3] T=2   │
└────────┬─────────┘
         │
         │ <-- 应用处理 -->
         │     ViewRootImpl
         │     dispatchInputEvent
         │     View.onTouchEvent
         │     ...
         │     finishInputEvent()
         │
         v
T4: 收到finish响应
    |
    v
┌──────────────────┐
│   WaitQueue      │ ← finishDispatchCycleLocked
│   [Event2] T=1   │   从队列移除Event1
│   [Event3] T=2   │
└──────────────────┘

如果在T4之前，有新事件到达同一窗口：
    → checkWindowReadyForMoreInputLocked
    → 检查WaitQueue中最旧事件
    → 如果 (currentTime - Event1.deliveryTime) > 5000ms
    → 触发ANR！
```

## 关键时间常量

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

// ANR超时时间
constexpr std::chrono::duration DEFAULT_INPUT_DISPATCHING_TIMEOUT = 
    std::chrono::milliseconds(5000); // 5秒

// 无焦点窗口超时
constexpr std::chrono::duration DEFAULT_NO_FOCUSED_WINDOW_TIMEOUT = 
    std::chrono::milliseconds(5000); // 5秒

// WaitQueue最大事件数
constexpr size_t MAX_QUEUED_EVENTS = 5;

// OutboundQueue最大事件数
constexpr size_t MAX_OUTBOUND_QUEUE_SIZE = 50;
```

## Dumpsys输出示例

```bash
$ adb shell dumpsys input

INPUT DISPATCHER STATE:
  DispatchEnabled: 1
  DispatchFrozen: 0
  FocusedApplication: <null>
  FocusedWindow: name='Window{abc1234 u0 com.example.app/MainActivity}'

  InboundQueue: length=2
    MotionEvent(eventTime=12345678, action=DOWN)
    MotionEvent(eventTime=12345690, action=MOVE)

  Connections:
    0: channelName='Window{abc1234...}', status=NORMAL
       OutboundQueue: length=0
       WaitQueue: length=3
         0: seq=100, age=100ms, MotionEvent(action=MOVE)
         1: seq=101, age=150ms, MotionEvent(action=MOVE)
         2: seq=102, age=200ms, MotionEvent(action=MOVE)
       
    1: channelName='Window{def5678...}', status=NOT_RESPONDING
       OutboundQueue: length=5
       WaitQueue: length=5
         0: seq=200, age=5500ms, MotionEvent(action=DOWN) ← ANR!
         1: seq=201, age=5400ms, MotionEvent(action=MOVE)
         ...
```

从dumpsys可以看到：
- InboundQueue的积压情况
- 每个Connection的OutboundQueue和WaitQueue状态
- 事件的等待时间（age）
- 哪个窗口处于NOT_RESPONDING状态

## 总结

核心要点：

1. **三个队列的职责清晰**：
   - InboundQueue：全局队列，所有事件入口
   - OutboundQueue：每连接队列，待发送事件
   - WaitQueue：每连接队列，已发送等响应（**ANR监控**）

2. **ANR检测时机精确**：
   - 在`checkWindowReadyForMoreInputLocked`中
   - 当新事件需要分发到某窗口时
   - 检查该窗口的WaitQueue中最旧事件的等待时间

3. **deliveryTime是关键**：
   - 在`startDispatchCycleLocked`中记录
   - 表示事件发送到应用的时间
   - ANR计算公式：`currentTime - deliveryTime > 5000ms`

4. **异步通知机制**：
   - ANR检测后不直接调用AMS
   - 加入CommandQueue异步处理
   - 避免在关键路径上阻塞

这就是InputDispatcher完整的事件分发和ANR检测流程！
