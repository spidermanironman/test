# Input类型ANR详解 - 从System到APP的输入分发流程

## 目录
1. [Input ANR概述](#input-anr概述)
2. [System端到APP端的耗时分析](#system端到app端的耗时分析)
3. [输入分发到应用的详细流程](#输入分发到应用的详细流程)
4. [关键时间节点](#关键时间节点)
5. [ANR触发机制](#anr触发机制)

---

## Input ANR概述

### 什么是Input ANR？
Input ANR（Application Not Responding）是Android系统中最常见的ANR类型之一。当应用程序在规定时间内（通常是5秒）无法处理输入事件时，系统会触发ANR。

### Input ANR的触发条件
- **超时时间**: 5秒（INPUT_DISPATCHING_TIMEOUT）
- **触发场景**: 
  - 点击事件无响应
  - 触摸事件处理超时
  - 按键事件无响应

---

## System端到APP端的耗时分析

### 1. Kernel层 (硬件 → 驱动)
**耗时: < 1ms (通常几微秒)**

```
输入设备 → Kernel驱动 → /dev/input/eventX
```

**详细说明:**
- 触摸屏、键盘等硬件产生中断信号
- Kernel驱动捕获中断，读取硬件寄存器数据
- 将原始数据写入 `/dev/input/eventX` 设备节点
- 通过epoll机制通知上层有新事件

**关键代码路径:**
- `drivers/input/evdev.c` - 事件设备驱动
- `drivers/input/input.c` - Input子系统核心

---

### 2. InputReader线程 (读取与预处理)
**耗时: 1-5ms**

```
EventHub → InputReader → InputMapper → RawEvent → NotifyArgs
```

**详细流程:**

#### 2.1 EventHub读取原始事件 (< 1ms)
```cpp
// frameworks/native/services/inputflinger/reader/EventHub.cpp
size_t EventHub::getEvents(int timeoutMillis, RawEvent* buffer, size_t bufferSize) {
    // 从 /dev/input/eventX 读取原始输入事件
    // 使用 epoll_wait 等待事件
    // 将多个设备的事件统一读取到buffer中
}
```

**关键操作:**
- 使用 `epoll_wait()` 监听所有input设备节点
- 批量读取原始事件数据（input_event结构体）
- 包含时间戳、设备ID、事件类型、事件码、事件值

#### 2.2 InputReader处理 (1-3ms)
```cpp
// frameworks/native/services/inputflinger/reader/InputReader.cpp
void InputReader::loopOnce() {
    // 1. 从EventHub获取原始事件
    size_t count = mEventHub->getEvents(timeoutMillis, mEventBuffer, EVENT_BUFFER_SIZE);
    
    // 2. 处理每个事件
    processEventsLocked(mEventBuffer, count);
    
    // 3. 通知监听器
    mQueuedListener->flush();
}
```

**主要工作:**
- **事件解析**: 将原始事件转换为逻辑事件
- **坐标映射**: 触摸坐标校准和旋转适配
- **多点触控处理**: Slot机制管理多指触摸
- **设备配置**: 根据设备类型选择合适的Mapper
- **手势识别**: 基础手势（如长按、滑动）的初步判断

#### 2.3 InputMapper分类处理 (1-2ms)
不同类型的输入设备使用不同的Mapper：
- **TouchInputMapper**: 触摸屏事件
- **KeyboardInputMapper**: 键盘事件
- **CursorInputMapper**: 鼠标事件
- **JoystickInputMapper**: 游戏手柄

**TouchInputMapper关键处理:**
```cpp
void TouchInputMapper::process(const RawEvent* rawEvent) {
    // 处理触摸事件
    sync(); // 同步触摸状态
    
    // 生成MotionEvent通知
    NotifyMotionArgs args;
    args.eventTime = 事件时间戳;
    args.deviceId = 设备ID;
    args.action = ACTION_DOWN/MOVE/UP;
    args.pointerCoords = 触摸坐标;
    
    getListener()->notifyMotion(&args);
}
```

**耗时详解:**
- 单点触摸: 1-2ms
- 多点触摸: 2-3ms（需要处理多个指针）
- 复杂手势: 3-5ms（涉及手势识别算法）

---

### 3. InputDispatcher线程 (分发决策)
**耗时: 2-10ms**

```
InputDispatcher队列 → 查找目标窗口 → 检查ANR → 创建事件 → 发送到APP
```

#### 3.1 事件入队 (< 1ms)
```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
void InputDispatcher::notifyMotion(const NotifyMotionArgs* args) {
    // 创建MotionEntry
    MotionEntry* entry = new MotionEntry(args);
    
    // 加入待分发队列
    mInboundQueue.enqueueAtTail(entry);
    
    // 唤醒Dispatcher线程
    mLooper->wake();
}
```

#### 3.2 查找目标窗口 (1-5ms)
```cpp
int32_t InputDispatcher::findFocusedWindowTargetsLocked(...) {
    // 1. 获取当前焦点窗口
    sp<InputWindowHandle> focusedWindowHandle = 
        getValueByKey(mFocusedWindowHandlesByDisplay, displayId);
    
    // 2. 检查窗口状态
    if (窗口不可见 || 窗口正在动画 || 窗口已销毁) {
        return INPUT_EVENT_INJECTION_FAILED;
    }
    
    // 3. 检查窗口是否能接收输入
    if (!focusedWindowHandle->getInfo()->inputFeatures.pauseDispatch) {
        addWindowTargetLocked(focusedWindowHandle, ...);
    }
    
    return INPUT_EVENT_INJECTION_SUCCEEDED;
}
```

**查找窗口的复杂度:**
- **触摸事件**: 需要遍历所有窗口，进行坐标碰撞检测 (2-5ms)
  - 按Z-order从上到下遍历
  - 检查触摸点是否在窗口区域内
  - 考虑窗口透明度、遮挡关系、触摸区域设置
- **按键事件**: 直接使用焦点窗口 (< 1ms)
- **多窗口模式**: 耗时增加 (5-10ms)

#### 3.3 ANR检查 (1-2ms)
```cpp
bool InputDispatcher::checkInjectionPermission(...) {
    // 检查是否应该触发ANR
    nsecs_t currentTime = now();
    
    // 检查上一个事件是否还在处理中
    if (connection->inputState.pendingEvents.size() > 0) {
        nsecs_t age = currentTime - oldestPendingEventTime;
        
        if (age > ANR_TIMEOUT) { // 5秒
            // 触发ANR
            onANRLocked(connection);
        }
    }
}
```

**ANR检查机制:**
- 维护每个连接的待处理事件队列
- 计算最早未完成事件的等待时间
- 超过5秒触发ANR流程
- 生成ANR trace和日志

#### 3.4 事件封装与发送 (1-3ms)
```cpp
void InputDispatcher::dispatchEventLocked(...) {
    // 1. 创建DispatchEntry
    DispatchEntry* dispatchEntry = new DispatchEntry(eventEntry);
    
    // 2. 加入连接的outboundQueue
    connection->outboundQueue.enqueueAtTail(dispatchEntry);
    
    // 3. 发送到Socket
    status_t status = connection->inputPublisher.publishMotionEvent(...);
    
    // 4. 记录发送时间（用于ANR检测）
    dispatchEntry->deliveryTime = now();
}
```

**耗时分析:**
- 事件序列化: 1-2ms
- Socket写入: < 1ms（非阻塞）
- 特殊情况（队列满）: 可能阻塞 5-10ms

---

### 4. Binder/Socket通信 (进程间传输)
**耗时: 1-3ms**

```
InputDispatcher → Socket → InputEventReceiver (APP进程)
```

**详细机制:**

#### 4.1 通信方式
Android使用 **Unix Domain Socket** 而非Binder进行输入事件传输：

```cpp
// System进程（InputDispatcher）
InputChannel::sendMessage() {
    // 通过Socket发送序列化后的InputEvent
    ssize_t nWrite = ::send(mFd, msg, msgLength, MSG_DONTWAIT | MSG_NOSIGNAL);
}

// APP进程（InputEventReceiver）
InputChannel::receiveMessage() {
    // 从Socket接收数据
    ssize_t nRead = ::recv(mFd, msg, msgLength, MSG_DONTWAIT);
}
```

**为什么用Socket而不是Binder？**
- **低延迟**: Socket传输比Binder快 (1-2ms vs 3-5ms)
- **优先级高**: 输入事件需要最快响应
- **单向通信**: 不需要Binder的双向RPC能力
- **数据量小**: 输入事件通常只有几百字节

#### 4.2 InputChannel创建
```cpp
// 创建Socket pair
InputChannel::openInputChannelPair(name, serverChannel, clientChannel) {
    int sockets[2];
    socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sockets);
    
    // server端留在system_server进程
    serverChannel = new InputChannel(name, sockets[0]);
    
    // client端通过Binder传递给APP进程
    clientChannel = new InputChannel(name, sockets[1]);
}
```

**传输过程:**
1. Window创建时，APP通过Binder向WMS请求InputChannel
2. WMS创建Socket pair，保留server端，将client端FD通过Binder传回
3. 后续事件通过Socket直接传输，无需Binder

#### 4.3 耗时因素
- **正常情况**: 1-2ms
- **系统繁忙**: 2-3ms
- **进程调度延迟**: 可能增加 5-10ms
- **CPU节流或DVFS**: 可能增加 10-20ms

---

### 5. APP进程接收 (主线程处理前)
**耗时: 1-5ms**

```
Looper监听 → InputEventReceiver回调 → 事件反序列化 → 放入队列
```

#### 5.1 Looper监听机制
```java
// frameworks/base/core/java/android/view/InputEventReceiver.java
public abstract class InputEventReceiver {
    
    // Native层通过JNI回调此方法
    private void dispatchInputEvent(int seq, InputEvent event) {
        mSeqMap.put(event.getSequenceNumber(), seq);
        
        // 调用子类实现（ViewRootImpl中的实现）
        onInputEvent(event);
    }
}
```

#### 5.2 ViewRootImpl接收
```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
final class WindowInputEventReceiver extends InputEventReceiver {
    
    @Override
    public void onInputEvent(InputEvent event) {
        // 1. 记录接收时间
        Trace.traceBegin(Trace.TRACE_TAG_VIEW, "deliverInputEvent");
        
        // 2. 放入待处理队列
        enqueueInputEvent(event, this, 0, true);
        
        Trace.traceEnd(Trace.TRACE_TAG_VIEW);
    }
}

void enqueueInputEvent(InputEvent event, ...) {
    // 创建QueuedInputEvent
    QueuedInputEvent q = obtainQueuedInputEvent(event, receiver, flags);
    
    // 加入队列尾部
    if (mPendingInputEventTail == null) {
        mPendingInputEventHead = q;
    } else {
        mPendingInputEventTail.mNext = q;
    }
    mPendingInputEventTail = q;
    mPendingInputEventCount++;
    
    // 请求处理（通过Choreographer调度）
    scheduleProcessInputEvents();
}
```

**耗时分析:**
- 事件反序列化: < 1ms
- 队列操作: < 1ms
- Trace记录: < 1ms
- 如果主线程繁忙: 可能等待 5-100ms+

---

### 6. APP主线程处理 (分发到View)
**耗时: 取决于应用实现，通常 1-50ms**

```
事件队列 → InputStage处理链 → DecorView → ViewGroup分发 → View处理
```

#### 6.1 InputStage处理链
```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
abstract class InputStage {
    private final InputStage mNext;
    
    public final void deliver(QueuedInputEvent q) {
        if (shouldDropInputEvent(q)) {
            finish(q, false);
        } else {
            apply(q, onProcess(q)); // 处理事件
        }
    }
    
    protected abstract int onProcess(QueuedInputEvent q);
}
```

**处理链顺序:**
1. **NativePreImeInputStage**: Native层IME前处理
2. **ViewPreImeInputStage**: View层IME前处理
3. **ImeInputStage**: 输入法处理
4. **EarlyPostImeInputStage**: IME后早期处理
5. **NativePostImeInputStage**: Native层IME后处理
6. **ViewPostImeInputStage**: **View层处理（关键！）**
7. **SyntheticInputStage**: 合成事件处理

#### 6.2 触摸事件分发 (核心流程)
```java
// ViewPostImeInputStage处理触摸事件
private int processPointerEvent(QueuedInputEvent q) {
    final MotionEvent event = (MotionEvent)q.mEvent;
    
    // 分发到DecorView
    boolean handled = mView.dispatchPointerEvent(event);
    
    return handled ? FINISH_HANDLED : FORWARD;
}

// View.java
public final boolean dispatchPointerEvent(MotionEvent event) {
    if (event.isTouchEvent()) {
        return dispatchTouchEvent(event); // 触摸事件
    } else {
        return dispatchGenericMotionEvent(event); // 鼠标等
    }
}
```

#### 6.3 ViewGroup事件分发
```java
// frameworks/base/core/java/android/view/ViewGroup.java
@Override
public boolean dispatchTouchEvent(MotionEvent ev) {
    boolean handled = false;
    
    // 1. 安全检查
    if (onFilterTouchEventForSecurity(ev)) {
        
        final int action = ev.getAction();
        
        // 2. 检查拦截
        final boolean intercepted;
        if (action == MotionEvent.ACTION_DOWN || mFirstTouchTarget != null) {
            final boolean disallowIntercept = (mGroupFlags & FLAG_DISALLOW_INTERCEPT) != 0;
            if (!disallowIntercept) {
                intercepted = onInterceptTouchEvent(ev); // 询问是否拦截
            } else {
                intercepted = false;
            }
        } else {
            intercepted = true;
        }
        
        // 3. 寻找目标子View (ACTION_DOWN时)
        if (!intercepted && action == MotionEvent.ACTION_DOWN) {
            for (int i = childrenCount - 1; i >= 0; i--) {
                final View child = getAndVerifyPreorderedView(...);
                
                // 检查触摸点是否在子View区域内
                if (!child.canReceivePointerEvents() || 
                    !isTransformedTouchPointInView(x, y, child, null)) {
                    continue;
                }
                
                // 尝试分发给子View
                if (dispatchTransformedTouchEvent(ev, false, child, idBitsToAssign)) {
                    // 子View处理了事件
                    mFirstTouchTarget = addTouchTarget(child, idBitsToAssign);
                    handled = true;
                    break;
                }
            }
        }
        
        // 4. 分发给目标View或自己处理
        if (mFirstTouchTarget == null) {
            // 没有子View处理，自己处理
            handled = dispatchTransformedTouchEvent(ev, canceled, null, ...);
        } else {
            // 分发给子View
            TouchTarget target = mFirstTouchTarget;
            while (target != null) {
                if (dispatchTransformedTouchEvent(ev, cancelChild, 
                    target.child, target.pointerIdBits)) {
                    handled = true;
                }
                target = target.next;
            }
        }
    }
    
    return handled;
}
```

**关键算法 - 触摸目标查找:**
```java
private boolean isTransformedTouchPointInView(float x, float y, View child, 
                                               PointF outLocalPoint) {
    // 1. 将父View坐标转换为子View坐标
    float[] point = getTempPoint();
    point[0] = x;
    point[1] = y;
    transformPointToViewLocal(point, child);
    
    // 2. 检查是否在子View范围内
    boolean isInView = child.pointInView(point[0], point[1]);
    
    return isInView;
}
```

#### 6.4 View处理事件
```java
// frameworks/base/core/java/android/view/View.java
public boolean dispatchTouchEvent(MotionEvent event) {
    boolean result = false;
    
    // 1. 检查accessibility
    if (event.isTargetAccessibilityFocus()) {
        // ... accessibility处理
    }
    
    // 2. 首先给OnTouchListener机会
    ListenerInfo li = mListenerInfo;
    if (li != null && li.mOnTouchListener != null
            && (mViewFlags & ENABLED_MASK) == ENABLED
            && li.mOnTouchListener.onTouch(this, event)) {
        result = true; // Listener消费了事件
    }
    
    // 3. 如果Listener没有消费，调用onTouchEvent
    if (!result && onTouchEvent(event)) {
        result = true;
    }
    
    return result;
}

public boolean onTouchEvent(MotionEvent event) {
    // 1. 检查View状态
    if ((mViewFlags & ENABLED_MASK) == DISABLED) {
        if (event.getAction() == MotionEvent.ACTION_UP && (mPrivateFlags & PFLAG_PRESSED) != 0) {
            setPressed(false);
        }
        return clickable; // disabled的View也可能消费事件
    }
    
    // 2. 处理触摸反馈
    if (clickable || (mViewFlags & TOOLTIP) == TOOLTIP) {
        switch (event.getAction()) {
            case MotionEvent.ACTION_DOWN:
                // 按下效果
                setPressed(true, x, y);
                checkForLongClick(0); // 开始长按检测
                break;
                
            case MotionEvent.ACTION_MOVE:
                // 检查是否移出View区域
                if (!pointInView(x, y, mTouchSlop)) {
                    removeTapCallback();
                    removeLongPressCallback();
                    setPressed(false);
                }
                break;
                
            case MotionEvent.ACTION_UP:
                // 抬起，触发点击
                if (!mHasPerformedLongPress && !mIgnoreNextUpEvent) {
                    if (!focusTaken) {
                        // 执行点击回调
                        performClickInternal();
                    }
                }
                setPressed(false);
                break;
                
            case MotionEvent.ACTION_CANCEL:
                setPressed(false);
                removeTapCallback();
                removeLongPressCallback();
                break;
        }
        
        return true; // 消费事件
    }
    
    return false;
}

private boolean performClickInternal() {
    return performClick();
}

public boolean performClick() {
    // 调用点击监听器
    ListenerInfo li = mListenerInfo;
    if (li != null && li.mOnClickListener != null) {
        playSoundEffect(SoundEffectConstants.CLICK);
        li.mOnClickListener.onClick(this); // 这里执行开发者的点击逻辑！
        return true;
    }
    return false;
}
```

**耗时分析:**
- **正常情况**: 1-10ms
  - View层级遍历: 1-5ms (取决于View树深度)
  - 事件分发逻辑: < 1ms
  - onClick回调执行: 取决于开发者代码
  
- **导致ANR的情况**: 
  - onClick中执行耗时操作 (网络请求、数据库操作、复杂计算)
  - View树过深 (超过10层)
  - onTouchEvent中执行耗时操作
  - 过多的layout/measure操作

---

### 7. 事件完成反馈
**耗时: 1-2ms**

```java
// frameworks/base/core/java/android/view/ViewRootImpl.java
private void finishInputEvent(QueuedInputEvent q) {
    if (q.mReceiver != null) {
        boolean handled = (q.mFlags & QueuedInputEvent.FLAG_FINISHED_HANDLED) != 0;
        
        // 通知system_server事件已处理完成
        q.mReceiver.finishInputEvent(q.mEvent, handled);
    }
}
```

```cpp
// Native层通过Socket发送完成信号
void InputConsumer::sendFinishedSignal(uint32_t seq, bool handled) {
    InputMessage msg;
    msg.header.type = InputMessage::TYPE_FINISHED;
    msg.body.finished.seq = seq;
    msg.body.finished.handled = handled;
    
    // 发送回InputDispatcher
    mChannel->sendMessage(&msg);
}
```

**InputDispatcher接收完成信号:**
```cpp
void InputDispatcher::handleReceiveCallback(...) {
    InputMessage msg;
    status_t status = connection->inputPublisher.receiveMessage(&msg);
    
    if (msg.header.type == InputMessage::TYPE_FINISHED) {
        // 从待处理队列移除
        connection->inputState.removeEvent(msg.body.finished.seq);
        
        // 重置ANR计时器
        resetANRTimeoutLocked(connection);
    }
}
```

---

## 完整时间链路总结

| 阶段 | 组件 | 耗时 | 累计时间 |
|------|------|------|----------|
| 1. 硬件中断 | Kernel驱动 | < 1ms | < 1ms |
| 2. 事件读取 | EventHub | < 1ms | 1-2ms |
| 3. 事件解析 | InputReader + Mapper | 1-5ms | 2-7ms |
| 4. 查找窗口 | InputDispatcher | 1-5ms | 3-12ms |
| 5. 进程通信 | Socket | 1-3ms | 4-15ms |
| 6. 事件接收 | InputEventReceiver | 1-5ms | 5-20ms |
| 7. View分发 | ViewRootImpl → View | 1-50ms | **6-70ms** |
| 8. 完成反馈 | Socket | 1-2ms | 7-72ms |

**正常情况: 7-50ms**  
**临界情况: 50-100ms**  
**ANR阈值: 5000ms (5秒)**

---

## 输入分发到应用的详细流程

### 完整流程图

```
硬件触摸屏
    ↓
Kernel驱动 (/dev/input/event0)
    ↓
[System Server进程]
    ↓
InputReader线程
    ├─ EventHub::getEvents()          // 读取原始事件
    ├─ InputReader::processEvents()   // 处理事件
    ├─ TouchInputMapper::process()    // 触摸事件映射
    └─ NotifyMotionArgs               // 通知参数
    ↓
InputDispatcher线程
    ├─ notifyMotion()                 // 接收通知
    ├─ findFocusedWindowTargets()     // 查找目标窗口
    ├─ checkANR()                     // ANR检测
    ├─ dispatchEvent()                // 分发事件
    └─ Socket发送
    ↓
[APP进程 - 主线程]
    ↓
Looper (epoll监听Socket)
    ↓
InputEventReceiver::dispatchInputEvent()
    ↓
WindowInputEventReceiver::onInputEvent()
    ↓
ViewRootImpl::enqueueInputEvent()
    ↓
ViewRootImpl::deliverInputEvent()
    ↓
InputStage处理链
    ↓
ViewPostImeInputStage::processPointerEvent()
    ↓
DecorView::dispatchTouchEvent()
    ↓
ViewGroup::dispatchTouchEvent()        // 递归查找子View
    ├─ onInterceptTouchEvent()         // 是否拦截？
    ├─ 查找子View (遍历children)
    └─ dispatchTransformedTouchEvent()
    ↓
View::dispatchTouchEvent()
    ├─ OnTouchListener::onTouch()     // 优先给Listener
    └─ onTouchEvent()                 // View自己处理
        └─ ACTION_UP → performClick()
            └─ OnClickListener::onClick()  // 🎯 开发者代码在这里！
    ↓
ViewRootImpl::finishInputEvent()       // 完成反馈
    ↓
Socket发送完成信号
    ↓
[System Server进程]
    ↓
InputDispatcher接收完成信号
    └─ 重置ANR计时器
```

---

## 关键时间节点

### 1. 事件产生时间
```cpp
// Kernel层记录的事件时间戳
struct input_event {
    struct timeval time;  // 硬件产生中断的时间
    __u16 type;
    __u16 code;
    __s32 value;
};
```

### 2. InputDispatcher发送时间
```cpp
dispatchEntry->deliveryTime = now(); // 发送到APP的时间
```

### 3. APP接收时间
```java
// ViewRootImpl.WindowInputEventReceiver
@Override
public void onInputEvent(InputEvent event) {
    Trace.traceBegin(Trace.TRACE_TAG_VIEW, "deliverInputEvent");
    // 当前时间 = APP接收时间
}
```

### 4. APP完成处理时间
```java
private void finishInputEvent(QueuedInputEvent q) {
    // 当前时间 = 处理完成时间
}
```

### ANR判定
```cpp
// InputDispatcher.cpp
nsecs_t timeout = 5000 * 1000000LL; // 5秒 (纳秒)
nsecs_t currentTime = now();
nsecs_t waitDuration = currentTime - dispatchEntry->deliveryTime;

if (waitDuration > timeout) {
    // 触发ANR！
    onANRLocked(currentTime, connection, ...);
}
```

---

## ANR触发机制

### 1. ANR检测时机
InputDispatcher在以下时机检查ANR：
- **发送新事件前**: 检查是否有事件超时
- **接收完成信号时**: 更新最后响应时间
- **定期轮询**: 每隔一定时间主动检查

### 2. ANR触发条件
```cpp
bool InputDispatcher::checkForANR(Connection* connection) {
    // 条件1: 有待处理的事件
    if (connection->inputState.isEmpty()) {
        return false;
    }
    
    // 条件2: 最早的事件已超时5秒
    DispatchEntry* oldestEntry = connection->findOldestEntry();
    nsecs_t age = now() - oldestEntry->deliveryTime;
    
    if (age > ANR_TIMEOUT) {
        return true; // 触发ANR
    }
    
    return false;
}
```

### 3. ANR信息收集
```cpp
void InputDispatcher::onANRLocked(...) {
    // 1. 记录ANR日志
    ALOGE("ANR in %s, reason: %s", connection->getInputChannelName().c_str(), reason);
    
    // 2. 收集系统状态
    dumpDispatchStateLocked(); // Dispatcher状态
    
    // 3. 通知AMS (Activity Manager Service)
    mPolicy->notifyANR(token, reason);
    
    // 4. AMS会：
    //    - 收集应用traces (通过发送SIGQUIT信号)
    //    - 生成ANR报告 (/data/anr/traces.txt)
    //    - 显示ANR对话框或直接杀死应用
}
```

### 4. ANR Trace内容
```
----- Input dispatching timeout info -----
Application not responding
Reason: Input dispatching timed out (Waiting to send key event because the focused window has not finished processing all of the input events that were previously delivered to it.)

Window: Window{abc1234 u0 com.example.app/com.example.MainActivity}

Input event details:
  eventTime: 1234567890000
  deviceId: 3
  source: TOUCHSCREEN
  action: ACTION_DOWN
  pointerCount: 1

Dispatcher state:
  Pending events: 5
  Oldest pending event age: 5234ms
  
Application traces: (main thread)
  at com.example.MainActivity.onClick(MainActivity.java:123)
  at android.view.View.performClick(View.java:7125)
  at android.view.View.onTouchEvent(View.java:14300)
  ...
```

---

## 避免Input ANR的最佳实践

### 1. 不要在主线程执行耗时操作
```java
// ❌ 错误示例
button.setOnClickListener(v -> {
    // 网络请求 - 会导致ANR！
    String result = httpClient.get("https://api.example.com/data");
    updateUI(result);
});

// ✅ 正确示例
button.setOnClickListener(v -> {
    new Thread(() -> {
        String result = httpClient.get("https://api.example.com/data");
        runOnUiThread(() -> updateUI(result));
    }).start();
    
    // 或者使用更现代的方式
    // viewModel.fetchData(); // 在ViewModel中使用协程
});
```

### 2. 优化View层级
```xml
<!-- ❌ 过深的View层级 -->
<LinearLayout>
    <LinearLayout>
        <LinearLayout>
            <LinearLayout>
                <Button />  <!-- 层级太深！-->
            </LinearLayout>
        </LinearLayout>
    </LinearLayout>
</LinearLayout>

<!-- ✅ 使用ConstraintLayout扁平化 -->
<ConstraintLayout>
    <Button />  <!-- 只有一层！ -->
</ConstraintLayout>
```

### 3. 避免在onTouchEvent中做复杂计算
```java
@Override
public boolean onTouchEvent(MotionEvent event) {
    switch (event.getAction()) {
        case MotionEvent.ACTION_MOVE:
            // ❌ 避免在这里做复杂计算
            // complexCalculation();
            
            // ✅ 只做必要的坐标记录
            mLastX = event.getX();
            mLastY = event.getY();
            invalidate(); // 请求重绘
            break;
    }
    return true;
}
```

### 4. 使用StrictMode检测
```java
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(new StrictMode.ThreadPolicy.Builder()
        .detectDiskReads()
        .detectDiskWrites()
        .detectNetwork()
        .penaltyLog()
        .penaltyDeath() // 开发时崩溃，强制修复
        .build());
}
```

### 5. 监控主线程消息队列
```java
Looper.getMainLooper().setMessageLogging(new Printer() {
    @Override
    public void println(String msg) {
        if (msg.startsWith(">>>>> Dispatching")) {
            mStartTime = System.currentTimeMillis();
        } else if (msg.startsWith("<<<<< Finished")) {
            long duration = System.currentTimeMillis() - mStartTime;
            if (duration > 100) { // 超过100ms
                Log.w("Performance", "Long message: " + duration + "ms");
            }
        }
    }
});
```

---

## 总结

### System端关键组件
1. **InputReader**: 负责从底层读取和预处理输入事件 (1-5ms)
2. **InputDispatcher**: 负责查找目标窗口和分发事件 (2-10ms)
3. **ANR检测**: 监控事件处理时间，超过5秒触发ANR

### APP端关键流程
1. **事件接收**: InputEventReceiver通过Socket接收事件 (1-5ms)
2. **事件分发**: ViewRootImpl → DecorView → ViewGroup → View (1-50ms)
3. **开发者代码**: onClick等回调中的业务逻辑 (**关键！**)
4. **完成反馈**: 通知system_server处理完成 (1-2ms)

### 关键数字
- **正常响应时间**: 7-50ms
- **ANR阈值**: 5000ms (5秒)
- **System端耗时**: 4-20ms
- **APP端耗时**: 取决于开发者代码实现

**Input ANR的根本原因: APP主线程在5秒内未能完成事件处理并反馈给系统。**
