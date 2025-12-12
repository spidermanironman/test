# InputDispatcher到ANR的详细流程

## 概述

InputDispatcher是Android系统中负责分发输入事件（触摸、按键等）的核心组件。当应用无法及时处理输入事件时，InputDispatcher会检测到并触发ANR（Application Not Responding）。本文详细解释这个流程，重点关注三个关键队列：InboundQueue、OutboundQueue和WaitQueue。

## 核心架构

### 1. InputDispatcher的主要组件

```
InputReader → InputDispatcher → Application Window
                    ↓
            ANR Detection Logic
```

### 2. 三个关键队列

#### 2.1 InboundQueue (IQ - 入站队列)
- **作用**：存储从InputReader接收到的原始输入事件
- **特点**：
  - 事件首先进入这个队列
  - 等待被分发到目标窗口
  - FIFO（先进先出）顺序处理

#### 2.2 OutboundQueue (OQ - 出站队列)
- **作用**：存储已经决定发送给特定窗口但还未发送的事件
- **特点**：
  - 每个Connection（连接）都有自己的OutboundQueue
  - 事件已经完成目标窗口的查找
  - 等待通过Socket发送给应用进程

#### 2.3 WaitQueue (WQ - 等待队列)
- **作用**：存储已发送给应用但还未收到处理完成响应的事件
- **特点**：
  - 每个Connection都有自己的WaitQueue
  - 用于跟踪未完成的事件
  - **ANR检测的关键队列**

## 详细流程

### 阶段1：事件接收与入队 (InboundQueue)

```
InputReader (InputThread)
    ↓
notifyMotion() / notifyKey()
    ↓
InputDispatcher::notifyMotion()
    ↓
enqueueInboundEventLocked()
    ↓
mInboundQueue.push_back(event)
    ↓
触发 mLooper->wake()
```

**关键代码逻辑**：
```cpp
void InputDispatcher::notifyMotion(const NotifyMotionArgs* args) {
    // 创建MotionEntry
    MotionEntry* newEntry = new MotionEntry(...);
    
    // 加入InboundQueue
    enqueueInboundEventLocked(newEntry);
}

void InputDispatcher::enqueueInboundEventLocked(EventEntry* entry) {
    mInboundQueue.push_back(entry);
    
    // 唤醒Dispatcher线程处理
    mLooper->wake();
}
```

### 阶段2：事件分发决策 (InboundQueue → OutboundQueue)

```
InputDispatcher Thread循环
    ↓
dispatchOnce()
    ↓
dispatchOnceInnerLocked()
    ↓
从mInboundQueue取出事件
    ↓
findFocusedWindowTargetsLocked() / findTouchedWindowTargetsLocked()
    ↓
确定目标Window
    ↓
检查ANR状态 (关键!)
    ↓
dispatchEventLocked()
    ↓
prepareDispatchCycleLocked()
    ↓
enqueueDispatchEntriesLocked()
    ↓
事件加入Connection->outboundQueue
```

**关键代码逻辑**：
```cpp
void InputDispatcher::dispatchOnceInnerLocked(nsecs_t* nextWakeupTime) {
    // 从InboundQueue获取事件
    mPendingEvent = mInboundQueue.front();
    mInboundQueue.pop_front();
    
    // 根据事件类型查找目标窗口
    InputEventInjectionResult injectionResult;
    if (mPendingEvent->type == EventEntry::Type::KEY) {
        injectionResult = findFocusedWindowTargetsLocked(...);
    } else if (mPendingEvent->type == EventEntry::Type::MOTION) {
        injectionResult = findTouchedWindowTargetsLocked(...);
    }
    
    // 分发到目标窗口
    dispatchEventLocked(currentTime, mPendingEvent, inputTargets);
}

void InputDispatcher::dispatchEventLocked(...) {
    for (const InputTarget& inputTarget : inputTargets) {
        prepareDispatchCycleLocked(currentTime, connection, eventEntry, inputTarget);
    }
}

void InputDispatcher::enqueueDispatchEntriesLocked(...) {
    // 将事件加入Connection的outboundQueue
    connection->outboundQueue.push_back(dispatchEntry);
    
    // 开始发送
    startDispatchCycleLocked(currentTime, connection);
}
```

### 阶段3：事件发送 (OutboundQueue → WaitQueue)

```
startDispatchCycleLocked()
    ↓
从connection->outboundQueue取出事件
    ↓
通过Socket发送到应用进程
    ↓
publish(connection->inputPublisher)
    ↓
事件移动到connection->waitQueue
    ↓
记录发送时间戳 (deliveryTime)
```

**关键代码逻辑**：
```cpp
void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection) {
    while (!connection->outboundQueue.empty()) {
        DispatchEntry* dispatchEntry = connection->outboundQueue.front();
        
        // 通过InputPublisher发送事件
        status_t status = connection->inputPublisher.publishMotionEvent(...);
        
        if (status == OK) {
            // 从outboundQueue移除
            connection->outboundQueue.erase(connection->outboundQueue.begin());
            
            // 加入waitQueue等待应用响应
            connection->waitQueue.push_back(dispatchEntry);
            
            // 记录发送时间
            dispatchEntry->deliveryTime = currentTime;
        }
    }
}
```

### 阶段4：事件处理完成 (WaitQueue)

```
应用进程处理事件
    ↓
调用finishInputEvent()
    ↓
通过Socket发送完成信号
    ↓
InputDispatcher::handleReceiveCallback()
    ↓
finishDispatchCycleLocked()
    ↓
从connection->waitQueue移除事件
```

**关键代码逻辑**：
```cpp
int InputDispatcher::handleReceiveCallback(int fd, int events, void* data) {
    Connection* connection = static_cast<Connection*>(data);
    
    // 接收应用的完成响应
    status_t status = connection->inputPublisher.receiveFinishedSignal(...);
    
    finishDispatchCycleLocked(currentTime, connection, seq, handled);
}

void InputDispatcher::finishDispatchCycleLocked(...) {
    // 从waitQueue中找到并移除已完成的事件
    DispatchEntry* dispatchEntry = connection->findWaitQueueEntry(seq);
    connection->waitQueue.erase(dispatchEntry);
    
    // 释放资源
    delete dispatchEntry;
}
```

## ANR检测机制

### 触发时机

ANR检测主要在**阶段2（分发决策）**时进行，检查的是**WaitQueue**的状态。

### 检测逻辑

```cpp
InputEventInjectionResult InputDispatcher::findFocusedWindowTargetsLocked(...) {
    // 获取焦点窗口
    sp<InputWindowHandle> focusedWindowHandle = getFocusedWindowLocked();
    sp<Connection> connection = getConnectionLocked(focusedWindowHandle->getToken());
    
    // 检查连接状态和waitQueue
    if (connection->waitQueue.size() >= MAX_QUEUED_EVENTS) {
        // waitQueue堆积过多，可能无响应
        return InputEventInjectionResult::FAILED;
    }
    
    // 检查最旧事件的等待时间
    if (!connection->waitQueue.empty()) {
        DispatchEntry* oldestEntry = connection->waitQueue.front();
        nsecs_t waitDuration = currentTime - oldestEntry->deliveryTime;
        
        if (waitDuration > ANR_TIMEOUT) {
            // 触发ANR
            onANRLocked(currentTime, connection, focusedWindowHandle, ...);
            return InputEventInjectionResult::TIMED_OUT;
        }
    }
    
    return InputEventInjectionResult::SUCCEEDED;
}
```

### ANR超时时间

- **按键事件（Key Event）**：5秒
- **触摸事件（Motion Event）**：5秒
- **前台服务**：5秒
- **后台服务**：10秒

### ANR触发条件

1. **WaitQueue不为空**：说明有事件已发送但未完成
2. **最旧事件超时**：`currentTime - deliveryTime > ANR_TIMEOUT`
3. **新事件到达**：当新事件需要分发到同一窗口时，检测到旧事件超时

### ANR处理流程

```
检测到ANR
    ↓
onANRLocked()
    ↓
收集诊断信息：
  - waitQueue中的事件列表
  - outboundQueue中的事件
  - 窗口信息
  - 应用进程状态
    ↓
通知AMS (ActivityManagerService)
    ↓
AMS::appNotResponding()
    ↓
生成ANR日志和traces
    ↓
显示ANR对话框（可选）
```

**关键代码逻辑**：
```cpp
void InputDispatcher::onANRLocked(nsecs_t currentTime,
        const sp<Connection>& connection,
        const sp<InputWindowHandle>& windowHandle, ...) {
    // 收集ANR诊断信息
    String8 reason = getApplicationWindowLabel(windowHandle);
    
    // 记录waitQueue状态
    ALOGE("Application is not responding: %s. "
          "It has %zu events waiting in the queue.",
          reason.c_str(), connection->waitQueue.size());
    
    // 通知CommandQueue，异步通知AMS
    std::unique_ptr<CommandEntry> commandEntry = 
        std::make_unique<CommandEntry>(&InputDispatcher::doNotifyANRLockedInterruptible);
    commandEntry->connection = connection;
    commandEntry->windowHandle = windowHandle;
    
    mCommandQueue.push_back(std::move(commandEntry));
}

void InputDispatcher::doNotifyANRLockedInterruptible(CommandEntry* commandEntry) {
    // 调用到Java层的InputManagerService
    mPolicy->notifyANR(token, reason);
    
    // 最终调用到ActivityManagerService
    // AMS会dump进程堆栈，生成traces.txt
}
```

## 完整流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                        InputReader Thread                        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │ InboundQueue │ ← 事件首先到达这里
                  │   (FIFO)     │
                  └──────┬───────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              InputDispatcher Thread (dispatchOnce)               │
│                                                                   │
│  1. 从InboundQueue取事件                                          │
│  2. 查找目标窗口 (findFocusedWindow/findTouchedWindow)           │
│  3. **检查目标窗口的WaitQueue** ← ANR检测点                       │
│     - 检查waitQueue大小                                           │
│     - 检查最旧事件的等待时间                                      │
│     - 超时则触发ANR                                               │
│  4. 如果正常，将事件加入目标窗口的OutboundQueue                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          ┌──────────────────────────────┐
          │  Connection (每个窗口一个)    │
          │                               │
          │  ┌��───────────────┐           │
          │  │ OutboundQueue  │ ← 等待发送 │
          │  └───────┬────────┘           │
          │          │                    │
          │          ▼                    │
          │  [通过Socket发送]              │
          │          │                    │
          │          ▼                    │
          │  ┌────────────────┐           │
          │  │   WaitQueue    │ ← ANR监控  │
          │  │  (等待finish)   │           │
          │  └───────┬────────┘           │
          └──────────┼────────────────────┘
                     │
                     ▼
          ┌─────────────────────┐
          │   应用进程处理事件    │
          │  (ViewRootImpl)     │
          └──────────┬──────────┘
                     │
                     ▼
          finishInputEvent() 响应
                     │
                     ▼
          从WaitQueue移除 (正常完成)
```

## 关键时间节点

| 时间节点 | 事件状态 | 队列位置 | 说明 |
|---------|---------|---------|------|
| T0 | 事件产生 | InboundQueue | InputReader报告事件 |
| T1 | 等待分发 | InboundQueue | 等待Dispatcher处理 |
| T2 | 分发决策 | - | 查找目标窗口，**ANR检测点** |
| T3 | 等待发送 | OutboundQueue | 已确定目标，准备发送 |
| T4 | 已发送 | WaitQueue | 事件已发送，等待应用响应 |
| T5 | 处理完成 | - | 应用返回finish，从WaitQueue移除 |

**ANR触发条件**：`T2 - T4(某个旧事件) > 5秒`

## 常见ANR场景分析

### 场景1：主线程阻塞

```
InboundQueue: [Event1, Event2, Event3] → 持续增长
              ↓
OutboundQueue: [Event0] → 无法发送，因为Socket缓冲区满
              ↓
WaitQueue: [很多旧事件] → 应用无响应，事件堆积
              ↓
触发ANR: 新事件到达时检测到WaitQueue中有超时事件
```

**原因**：应用主线程执行耗时操作（IO、死锁、CPU密集计算）

### 场景2：事件处理缓慢

```
WaitQueue: [Event1(T=0s), Event2(T=1s), ..., Event10(T=4.5s)]
              ↓
新Event11到达时检测
              ↓
Event1等待时间 = 当前时间 - Event1.deliveryTime > 5秒
              ↓
触发ANR
```

**原因**：每个事件处理时间过长，累积导致超时

### 场景3：系统繁忙

```
多个窗口同时接收事件
              ↓
CPU资源不足
              ↓
所有WaitQueue都在增长
              ↓
某个窗口的最旧事件超时
              ↓
触发ANR
```

**原因**：系统整体负载过高，进程调度不及时

## 调试技巧

### 1. 查看Dumpsys信息

```bash
adb shell dumpsys input
```

输出包含：
- InboundQueue当前大小
- 每个Connection的OutboundQueue和WaitQueue状态
- 最后一次ANR的详细信息

### 2. 查看EventLog

```bash
adb logcat -b events | grep input
```

关键日志：
- `input_interaction`: 事件分发
- `input_focus`: 焦点变化
- `am_anr`: ANR发生

### 3. 分析Traces文件

```bash
adb pull /data/anr/traces.txt
```

查看ANR时刻的堆栈信息：
- 主线程在做什么
- 是否有锁竞争
- 是否有死锁

## 优化建议

### 应用层面

1. **避免主线程耗时操作**
   - 将IO、网络请求移到后台线程
   - 使用AsyncTask、RxJava、Coroutines等

2. **优化事件处理逻辑**
   - 简化View层级，减少measure/layout时间
   - 避免在onTouchEvent中执行复杂计算

3. **使用TraceView/Systrace分析**
   - 找出耗时的方法调用
   - 优化热点代码

### 系统层面

1. **调整ANR超时时间**（调试用）
   ```cpp
   // frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
   constexpr nsecs_t DEFAULT_INPUT_DISPATCHING_TIMEOUT = 5000ms;
   ```

2. **监控WaitQueue大小**
   - 添加日志监控队列深度
   - 预警机制

3. **优化InputDispatcher性能**
   - 减少锁竞争
   - 优化事件过滤逻辑

## 总结

InputDispatcher的ANR检测流程核心要点：

1. **三个队列的作用**：
   - InboundQueue：存储待处理的原始事件
   - OutboundQueue：存储待发送的事件
   - WaitQueue：存储已发送待响应的事件（**ANR监控关键**）

2. **ANR检测时机**：
   - 在分发新事件时检查目标窗口的WaitQueue
   - 如果WaitQueue中最旧事件超过5秒未完成，触发ANR

3. **事件生命周期**：
   ```
   产生 → InboundQueue → 分发决策(ANR检测) → OutboundQueue → 
   发送 → WaitQueue → 应用处理 → finish → 移除
   ```

4. **ANR的根本原因**：
   - 应用无法及时处理已发送的事件
   - WaitQueue中的事件长时间得不到finish响应
   - 当新事件到达时触发超时检测

理解这个流程对于诊断和解决Android应用的ANR问题至关重要。
