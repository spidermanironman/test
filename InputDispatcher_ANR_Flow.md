# InputDispatcher 透传到 ANR 的详细流程

## 概述

InputDispatcher 是 Android 系统中负责分发输入事件（触摸、按键等）的核心组件。当应用无法及时处理输入事件时，系统会触发 ANR（Application Not Responding）。本文档详细解释从输入事件到达 InputDispatcher 到触发 ANR 的完整流程。

## 核心组件

### 1. InputDispatcher 线程
- **位置**: `frameworks/native/services/inputflinger/InputDispatcher.cpp`
- **职责**: 负责接收输入事件并分发给目标应用窗口
- **线程**: 运行在 system_server 进程中的独立线程

### 2. 关键队列

#### 2.1 InboundQueue (iq) - 输入队列
- **作用**: 存储从 InputReader 接收到的原始输入事件
- **位置**: `InputDispatcher::mInboundQueue`
- **特点**: 
  - FIFO（先进先出）队列
  - 由 InputReader 线程填充
  - 由 InputDispatcher 线程消费

#### 2.2 WaitQueue (wq) - 等待队列
- **作用**: 存储已发送给应用但尚未收到确认的事件
- **位置**: `InputDispatcher::mWaitQueue` (每个连接一个)
- **特点**:
  - 用于跟踪已发送但未完成的事件
  - 每个应用连接（Connection）都有自己的等待队列
  - 用于 ANR 检测

#### 2.3 OutboundQueue - 出站队列
- **作用**: 存储准备发送给目标应用的事件
- **位置**: `InputDispatcher::Connection::outboundQueue`
- **特点**:
  - 每个连接（Connection）都有自己的出站队列
  - 事件在发送前会先进入此队列
  - 按优先级排序

## 详细流程

### 阶段 1: 输入事件接收

```
InputReader Thread
    ↓ (写入)
InboundQueue (iq)
    ↓ (读取)
InputDispatcher Thread
```

**代码流程**:
1. InputReader 线程从硬件读取输入事件
2. 调用 `InputDispatcher::notifyKey()` 或 `InputDispatcher::notifyMotion()`
3. 事件被添加到 `mInboundQueue`
4. InputDispatcher 线程被唤醒

### 阶段 2: 事件分发准备

```
InputDispatcher::dispatchOnce()
    ↓
处理 InboundQueue 中的事件
    ↓
找到目标窗口 (findFocusedWindowTarget())
    ↓
获取或创建 Connection 对象
```

**关键步骤**:
- `dispatchOnce()`: InputDispatcher 主循环函数
- `findFocusedWindowTarget()`: 查找当前获得焦点的窗口
- `getConnectionLocked()`: 获取与目标应用的连接对象

### 阶段 3: 事件入队到 OutboundQueue

```
InputDispatcher::enqueueInboundEventLocked()
    ↓
InputDispatcher::prepareDispatchCycleLocked()
    ↓
Connection::outboundQueue.push_back(event)
```

**代码位置**: `InputDispatcher.cpp::prepareDispatchCycleLocked()`

**关键逻辑**:
```cpp
// 伪代码示例
void InputDispatcher::prepareDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection, EventEntry* eventEntry) {
    // 1. 检查连接状态
    if (connection->status != Connection::STATUS_NORMAL) {
        return;
    }
    
    // 2. 创建 DispatchEntry
    DispatchEntry* dispatchEntry = new DispatchEntry(eventEntry);
    
    // 3. 添加到出站队列
    connection->outboundQueue.push_back(dispatchEntry);
    
    // 4. 如果队列为空，立即尝试发送
    if (connection->outboundQueue.size() == 1) {
        startDispatchCycleLocked(currentTime, connection);
    }
}
```

### 阶段 4: 事件发送到应用

```
startDispatchCycleLocked()
    ↓
从 outboundQueue 取出事件
    ↓
通过 InputChannel 发送到应用
    ↓
事件添加到 WaitQueue (wq)
```

**代码位置**: `InputDispatcher.cpp::startDispatchCycleLocked()`

**关键逻辑**:
```cpp
// 伪代码示例
void InputDispatcher::startDispatchCycleLocked(nsecs_t currentTime,
        const sp<Connection>& connection) {
    // 1. 从出站队列取出事件
    DispatchEntry* dispatchEntry = connection->outboundQueue.front();
    
    // 2. 通过 InputChannel 发送
    status_t status = connection->inputPublisher.publishKeyEvent(...);
    
    if (status == OK) {
        // 3. 从出站队列移除
        connection->outboundQueue.pop_front();
        
        // 4. 添加到等待队列（用于 ANR 检测）
        connection->waitQueue.push_back(dispatchEntry);
        
        // 5. 记录发送时间
        dispatchEntry->deliveryTime = currentTime;
        
        // 6. 设置 ANR 超时
        dispatchEntry->timeoutTime = currentTime + 
            (isKeyEvent ? KEY_DISPATCHING_TIMEOUT : 
                          TOUCH_DISPATCHING_TIMEOUT);
    }
}
```

### 阶段 5: 应用处理事件

```
应用主线程 (Main Thread)
    ↓
InputChannel 接收事件
    ↓
ViewRootImpl.dispatchInputEvent()
    ↓
应用处理事件 (onTouchEvent, onKeyDown 等)
    ↓
发送完成信号 (finishInputEvent)
```

**应用端流程**:
1. 应用通过 InputChannel 接收事件
2. ViewRootImpl 分发到对应的 View
3. View 处理事件（如 `onTouchEvent()`）
4. 处理完成后调用 `finishInputEvent()` 通知系统

### 阶段 6: 完成确认与 ANR 检测

```
应用发送 finishInputEvent
    ↓
InputDispatcher::finishInputEvent()
    ↓
从 WaitQueue 移除事件
    ↓
继续处理下一个事件
```

**ANR 检测机制**:

InputDispatcher 定期检查 WaitQueue 中的事件是否超时：

```cpp
// 伪代码示例
void InputDispatcher::checkAnrLocked() {
    nsecs_t currentTime = now();
    
    // 检查所有连接的等待队列
    for (auto& connection : mConnectionsByFd) {
        if (connection->waitQueue.empty()) {
            continue;
        }
        
        // 检查等待队列中的第一个事件
        DispatchEntry* oldestEntry = connection->waitQueue.front();
        
        // 如果超时，触发 ANR
        if (currentTime >= oldestEntry->timeoutTime) {
            // 计算超时时间
            nsecs_t timeout = oldestEntry->timeoutTime - oldestEntry->deliveryTime;
            
            // 触发 ANR
            onAnrLocked(connection, timeout);
            return;
        }
    }
}
```

**ANR 超时时间**:
- **按键事件 (KEY)**: `KEY_DISPATCHING_TIMEOUT` = 5秒
- **触摸事件 (TOUCH)**: `TOUCH_DISPATCHING_TIMEOUT` = 5秒（Android 5.0+）
- **无焦点窗口**: `DISPATCHING_TIMEOUT` = 5秒

### 阶段 7: ANR 触发

```
onAnrLocked()
    ↓
记录 ANR 信息
    ↓
发送 ANR 信号到应用进程
    ↓
ActivityManagerService 处理 ANR
    ↓
生成 ANR 日志和对话框
```

**代码位置**: `InputDispatcher.cpp::onAnrLocked()`

**关键逻辑**:
```cpp
// 伪代码示例
void InputDispatcher::onAnrLocked(const sp<Connection>& connection,
        nsecs_t timeout) {
    // 1. 记录 ANR 信息
    String8 reason = String8::format(
        "Input event dispatching timed out (reason: %s)",
        getReasonString(connection));
    
    // 2. 记录到日志
    ALOGE("Application is not responding: %s", reason.string());
    
    // 3. 通知 ActivityManagerService
    mPolicy->notifyAnr(connection->inputWindowHandle->applicationToken,
                       connection->inputWindowHandle->name);
    
    // 4. 记录 ANR 到系统日志
    // 这会导致生成 /data/anr/traces.txt
}
```

## 完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    InputReader Thread                       │
│  (从硬件读取输入事件)                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ notifyKey/notifyMotion()
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              InboundQueue (iq)                              │
│  [Event1] → [Event2] → [Event3] → ...                      │
└──────────────────────┬──────────────────────────────────────┘
                       │ dispatchOnce()
                       ↓
┌─────────────────────────────────────────────────────────────┐
│            InputDispatcher Thread                           │
│  - findFocusedWindowTarget()                                │
│  - getConnectionLocked()                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │ prepareDispatchCycleLocked()
                       ↓
┌─────────────────────────────────────────────────────────────┐
│         Connection::outboundQueue                           │
│  [DispatchEntry1] → [DispatchEntry2] → ...                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ startDispatchCycleLocked()
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              InputChannel (IPC)                             │
│  (通过 Binder/Unix Socket 发送到应用)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│         Connection::waitQueue (wq)                          │
│  [DispatchEntry1] ← (等待应用确认)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ (应用处理中...)
                       │
                       ↓ (如果超时)
┌─────────────────────────────────────────────────────────────┐
│              checkAnrLocked()                               │
│  - 检查 waitQueue 中的事件是否超时                          │
│  - 如果超时 → onAnrLocked()                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              onAnrLocked()                                  │
│  - 记录 ANR 日志                                            │
│  - 通知 ActivityManagerService                              │
│  - 生成 ANR 对话框                                          │
└─────────────────────────────────────────────────────────────┘
```

## 关键时间点

### 1. 事件发送时间 (deliveryTime)
- **记录位置**: `DispatchEntry::deliveryTime`
- **记录时机**: 事件成功发送到应用时
- **用途**: 计算事件在等待队列中的等待时间

### 2. 超时时间 (timeoutTime)
- **计算方式**: `deliveryTime + DISPATCHING_TIMEOUT`
- **默认值**: 5秒（KEY 和 TOUCH 事件）
- **检查频率**: InputDispatcher 每次 `dispatchOnce()` 时检查

### 3. ANR 触发条件
- WaitQueue 中的事件超过超时时间
- 应用主线程阻塞，无法处理输入事件
- 应用主线程处理事件时间过长（超过5秒）

## 常见 ANR 场景

### 场景 1: 主线程阻塞
```
应用主线程正在执行耗时操作
    ↓
无法及时处理输入事件
    ↓
WaitQueue 中的事件超时
    ↓
触发 ANR
```

### 场景 2: 主线程处理事件过慢
```
应用主线程处理 onTouchEvent()
    ↓
处理时间超过 5 秒
    ↓
无法发送 finishInputEvent()
    ↓
WaitQueue 中的事件超时
    ↓
触发 ANR
```

### 场景 3: 无焦点窗口
```
应用窗口失去焦点
    ↓
InputDispatcher 无法找到目标窗口
    ↓
事件在队列中等待
    ↓
超过超时时间
    ↓
触发 ANR
```

## 调试和监控

### 1. 查看队列状态
```bash
# 使用 systrace 查看
systrace.py --time=10 -o trace.html input

# 关键标签:
# - InputDispatcher::dispatchOnce
# - InputDispatcher::startDispatchCycleLocked
# - InputDispatcher::checkAnrLocked
```

### 2. 查看 ANR 日志
```bash
# 查看 ANR 日志
adb shell cat /data/anr/traces.txt

# 查看最近的 ANR
adb shell dumpsys dropbox --print | grep anr
```

### 3. 监控队列大小
- **InboundQueue**: 通常应该为空或很小
- **OutboundQueue**: 每个连接应该很小
- **WaitQueue**: 应该只包含正在处理的事件（通常1-2个）

## 性能优化建议

### 1. 应用端优化
- **避免主线程阻塞**: 将耗时操作移到后台线程
- **快速处理输入事件**: 确保 `onTouchEvent()` 等方法快速返回
- **及时调用 finishInputEvent**: 处理完成后立即通知系统

### 2. 系统端优化
- **合理设置超时时间**: 根据设备性能调整
- **优化事件分发逻辑**: 减少不必要的查找和排序
- **监控队列大小**: 及时发现异常情况

## 相关源码位置

### InputDispatcher 核心文件
- `frameworks/native/services/inputflinger/InputDispatcher.cpp`
- `frameworks/native/services/inputflinger/InputDispatcher.h`
- `frameworks/native/services/inputflinger/Connection.cpp`

### ANR 相关
- `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`
- `frameworks/base/services/core/java/com/android/server/am/AnrHelper.java`

### 应用端
- `frameworks/base/core/java/android/view/ViewRootImpl.java`
- `frameworks/base/core/java/android/view/InputChannel.java`

## 总结

InputDispatcher 到 ANR 的流程可以概括为：

1. **输入事件接收**: InputReader → InboundQueue (iq)
2. **事件分发准备**: 查找目标窗口，获取连接
3. **事件入队**: 添加到 OutboundQueue
4. **事件发送**: 通过 InputChannel 发送到应用
5. **等待确认**: 事件进入 WaitQueue (wq)，等待应用处理
6. **ANR 检测**: 定期检查 WaitQueue 中的事件是否超时
7. **ANR 触发**: 如果超时，调用 onAnrLocked() 触发 ANR

整个流程的关键在于 **WaitQueue**，它是 ANR 检测的核心。如果应用无法及时处理输入事件并发送确认，WaitQueue 中的事件就会超时，从而触发 ANR。
