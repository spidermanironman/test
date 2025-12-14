# Input类型ANR与输入分发到应用详解

## 一、概述

Input ANR（Application Not Responding）是Android系统中最常见的ANR类型之一，当用户的输入事件（如触摸、按键）在规定时间内没有得到应用的响应时触发。

### ANR超时阈值
- **普通应用**: 5秒
- **按键事件（KEY_EVENT）**: 5秒
- **触摸事件（MOTION_EVENT）**: 5秒

---

## 二、输入事件从System到APP的完整流程

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Hardware Layer                                      │
│                         (触摸屏/物理按键/传感器)                                   │
└─────────────────────────┬───────────────────────────────────────────────────────┘
                          │ ① 硬件中断
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Kernel Driver                                       │
│                    (/dev/input/eventX 设备节点)                                  │
└─────────────────────────┬───────────────────────────────────────────────────────┘
                          │ ② 内核事件上报
                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           System Server 进程                                     │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                        InputManagerService                               │    │
│  │  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │    │
│  │  │   InputReader    │───▶│  InputDispatcher │───▶│ InputChannel(S)  │   │    │
│  │  │    (读取线程)      │    │    (分发线程)     │    │   (服务端通道)    │   │    │
│  │  └──────────────────┘    └──────────────────┘    └────────┬─────────┘   │    │
│  └───────────────────────────────────────────────────────────│─────────────┘    │
└──────────────────────────────────────────────────────────────│──────────────────┘
                                                               │ ③ Socket通信
                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              APP 进程                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                        ViewRootImpl                                      │    │
│  │  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │    │
│  │  │ InputChannel(C)  │───▶│InputEventReceiver│───▶│  View Hierarchy  │   │    │
│  │  │   (客户端通道)    │    │   (事件接收器)    │    │    (视图层级)     │   │    │
│  │  └──────────────────┘    └──────────────────┘    └──────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、各阶段详细耗时分析

### 阶段1: 硬件到内核 (Hardware → Kernel)

| 环节 | 耗时范围 | 说明 |
|-----|---------|------|
| 硬件中断触发 | < 1ms | 触摸屏控制器产生中断信号 |
| 中断处理程序 | < 1ms | 内核响应中断，调用驱动程序 |
| 驱动事件封装 | < 1ms | 将原始数据封装为input_event结构 |
| 写入EventHub | < 1ms | 通过/dev/input/eventX节点上报 |

**总耗时**: 通常 < 5ms

### 阶段2: InputReader读取事件 (Kernel → InputReader)

```cpp
// 关键代码路径: frameworks/native/services/inputflinger/reader/InputReader.cpp

void InputReader::loopOnce() {
    // ① 从EventHub读取原始事件
    size_t count = mEventHub->getEvents(timeoutMillis, mEventBuffer, EVENT_BUFFER_SIZE);
    
    // ② 处理原始事件
    if (count) {
        processEventsLocked(mEventBuffer, count);
    }
    
    // ③ 将处理后的事件发送给InputDispatcher
    mQueuedListener->flush();
}
```

| 环节 | 耗时范围 | 说明 |
|-----|---------|------|
| EventHub::getEvents() | 0-5ms | 使用epoll等待/dev/input事件 |
| 事件解析处理 | < 1ms | 将raw event转换为NotifyArgs |
| 发送到InputDispatcher | < 1ms | 通过InputListenerInterface回调 |

**总耗时**: 通常 < 10ms

### 阶段3: InputDispatcher分发事件 (InputDispatcher → InputChannel)

```cpp
// 关键代码路径: frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

void InputDispatcher::dispatchOnce() {
    nsecs_t nextWakeupTime = LLONG_MAX;
    { 
        // ① 从队列中取出待分发事件
        if (!haveCommandsLocked()) {
            dispatchOnceInnerLocked(&nextWakeupTime);
        }
        
        // ② 执行命令队列
        if (runCommandsLockedInterruptible()) {
            nextWakeupTime = LLONG_MIN;
        }
    }
    
    // ③ 等待下一个事件或超时
    mLooper->pollOnce(timeoutMillis);
}
```

| 环节 | 耗时范围 | 说明 |
|-----|---------|------|
| 查找目标窗口 | < 2ms | findFocusedWindowTargetsLocked / findTouchedWindowTargetsLocked |
| 权限检查 | < 1ms | 检查应用是否有权接收输入 |
| 事件入队 | < 1ms | 将事件放入目标Connection的outboundQueue |
| Socket写入 | < 1ms | 通过InputChannel发送到APP进程 |

**重要时间点记录**:
```cpp
// 分发开始时间
entry->dispatchInProgress = true;
dispatchEntry->deliveryTime = currentTime;  // 关键时间戳！
```

**总耗时**: 通常 < 5ms

### 阶段4: APP进程接收事件 (InputChannel → InputEventReceiver)

```java
// 关键代码路径: frameworks/base/core/java/android/view/InputEventReceiver.java

public abstract class InputEventReceiver {
    // Native回调，当有输入事件到达时被调用
    private void dispatchInputEvent(int seq, InputEvent event) {
        // 记录接收时间
        mSeqMap.put(seq, event);
        onInputEvent(event);  // 子类实现
    }
}
```

| 环节 | 耗时范围 | 说明 |
|-----|---------|------|
| Socket读取 | < 1ms | 从InputChannel读取事件数据 |
| Native反序列化 | < 1ms | 将字节数据转换为InputEvent对象 |
| JNI回调 | < 1ms | 调用Java层的dispatchInputEvent |
| 事件排队 | < 1ms | 放入MessageQueue等待处理 |

**总耗时**: 通常 < 5ms

### 阶段5: ViewRootImpl处理事件 (InputEventReceiver → View)

```java
// 关键代码路径: frameworks/base/core/java/android/view/ViewRootImpl.java

final class WindowInputEventReceiver extends InputEventReceiver {
    @Override
    public void onInputEvent(InputEvent event) {
        // ① 入队到InputStage处理链
        enqueueInputEvent(event, this, 0, true);
    }
}

void doProcessInputEvents() {
    while (mPendingInputEventHead != null) {
        QueuedInputEvent q = mPendingInputEventHead;
        // ② 通过InputStage链处理事件
        deliverInputEvent(q);
    }
}
```

**InputStage处理链**:

```
┌───────────────────────────────────────────────────────────────┐
│                    InputStage Pipeline                         │
├───────────────────────────────────────────────────────────────┤
│  1. NativePreImeInputStage    - Native层预IME处理              │
│         ↓                                                      │
│  2. ViewPreImeInputStage      - View预IME处理                  │
│         ↓                                                      │
│  3. ImeInputStage             - 输入法处理                     │
│         ↓                                                      │
│  4. EarlyPostImeInputStage    - 早期后IME处理                  │
│         ↓                                                      │
│  5. NativePostImeInputStage   - Native层后IME处理              │
│         ↓                                                      │
│  6. ViewPostImeInputStage     - View事件分发 (核心！)          │
│         ↓                                                      │
│  7. SyntheticInputStage       - 合成事件处理                   │
└───────────────────────────────────────────────────────────────┘
```

| 环节 | 耗时范围 | 说明 |
|-----|---------|------|
| InputStage链处理 | 变化大 | 取决于每个Stage的处理逻辑 |
| IME处理 | 0-10ms | 如果需要输入法处理 |
| View事件分发 | 变化大 | **这是最容易出问题的阶段** |

### 阶段6: View Hierarchy事件分发 (View → 具体控件)

```java
// 触摸事件分发核心流程
public boolean dispatchTouchEvent(MotionEvent ev) {
    // ① Activity.dispatchTouchEvent
    //    ↓
    // ② PhoneWindow.superDispatchTouchEvent
    //    ↓
    // ③ DecorView.superDispatchTouchEvent
    //    ↓
    // ④ ViewGroup.dispatchTouchEvent (递归分发)
    //    ↓
    // ⑤ View.onTouchEvent (最终消费)
}
```

**详细分发流程**:

```java
// ViewGroup.dispatchTouchEvent() 核心逻辑
@Override
public boolean dispatchTouchEvent(MotionEvent ev) {
    boolean handled = false;
    
    // 1. 安全检查
    if (onFilterTouchEventForSecurity(ev)) {
        
        // 2. 拦截检查
        final boolean intercepted = onInterceptTouchEvent(ev);
        
        if (!intercepted) {
            // 3. 遍历子View寻找触摸目标
            for (int i = childrenCount - 1; i >= 0; i--) {
                if (child.dispatchTouchEvent(ev)) {
                    mFirstTouchTarget = addTouchTarget(child, idBitsToAssign);
                    break;
                }
            }
        }
        
        // 4. 分发给目标或自己处理
        if (mFirstTouchTarget == null) {
            handled = super.dispatchTouchEvent(ev);
        } else {
            handled = dispatchTransformedTouchEvent(ev, false, target.child, target.pointerIdBits);
        }
    }
    
    return handled;
}
```

| 环节 | 耗时范围 | 说明 |
|-----|---------|------|
| 事件过滤 | < 1ms | onFilterTouchEventForSecurity |
| 拦截判断 | < 1ms | onInterceptTouchEvent |
| 子View遍历 | 变化大 | **深层嵌套会显著增加耗时** |
| 实际事件处理 | 变化大 | **业务代码执行** |

---

## 四、关键时间戳与ANR判定

### InputDispatcher中的超时检测

```cpp
// frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp

nsecs_t InputDispatcher::getDispatchingTimeoutLocked(const sp<IBinder>& token) {
    // 默认超时时间
    return DEFAULT_INPUT_DISPATCHING_TIMEOUT;  // 5秒 = 5000000000ns
}

void InputDispatcher::doNotifyANRLockedInterruptible(CommandEntry* commandEntry) {
    // 当检测到ANR时，通知系统
    mPolicy->notifyANR(commandEntry->inputApplicationHandle,
                       commandEntry->inputChannel->getToken(),
                       commandEntry->reason);
}
```

### ANR触发条件判定

```cpp
// 检查是否超时
std::chrono::nanoseconds InputDispatcher::checkWindowNoResponseLocked(
        nsecs_t currentTime, 
        const sp<Connection>& connection,
        std::string& reason) {
    
    // 1. 检查等待队列中的事件
    if (!connection->waitQueue.empty()) {
        DispatchEntry* oldestEntry = connection->waitQueue.front();
        nsecs_t dispatchingTime = currentTime - oldestEntry->deliveryTime;
        
        if (dispatchingTime > timeout) {
            // 超时！触发ANR
            reason = "Waiting because ";
            reason += connection->inputChannel->getName();
            reason += " has a pending event";
            return timeout;
        }
    }
    
    return timeout;
}
```

### 关键时间点记录

| 时间点 | 记录位置 | 含义 |
|-------|---------|------|
| `eventTime` | InputEvent | 事件在硬件层产生的时间 |
| `readTime` | InputReader | InputReader读取到事件的时间 |
| `enqueueTime` | InputDispatcher | 事件入队到Dispatcher的时间 |
| `deliveryTime` | DispatchEntry | 事件发送到APP的时间 |
| `finishTime` | InputDispatcher | APP返回finish的时间 |

### 耗时计算公式

```
总耗时 = finishTime - eventTime

System侧耗时 = deliveryTime - eventTime
  = (readTime - eventTime)           // 内核到Reader
  + (enqueueTime - readTime)         // Reader到Dispatcher
  + (deliveryTime - enqueueTime)     // Dispatcher处理和发送

APP侧耗时 = finishTime - deliveryTime
  = (receiveTime - deliveryTime)     // 跨进程传输
  + (processTime)                    // 事件处理
  + (finishSendTime - processEndTime) // 返回完成信号
```

---

## 五、输入分发到应用的详细描述

### 5.1 InputChannel通信机制

InputChannel是System Server与APP进程之间的通信桥梁，基于Unix Socket实现。

```cpp
// 创建InputChannel对
status_t InputChannel::openInputChannelPair(const std::string& name,
        sp<InputChannel>& outServerChannel,
        sp<InputChannel>& outClientChannel) {
    
    int sockets[2];
    // 创建socket对
    if (socketpair(AF_UNIX, SOCK_SEQPACKET, 0, sockets)) {
        return -errno;
    }
    
    // 服务端Channel (System Server持有)
    outServerChannel = new InputChannel(name + " (server)", sockets[0]);
    
    // 客户端Channel (传给APP进程)
    outClientChannel = new InputChannel(name + " (client)", sockets[1]);
    
    return OK;
}
```

**数据流向**:

```
┌──────────────────────┐                    ┌──────────────────────┐
│   InputDispatcher    │                    │   ViewRootImpl       │
│   (System Server)    │                    │   (APP Process)      │
├──────────────────────┤                    ├──────────────────────┤
│                      │   InputMessage     │                      │
│  ServerChannel ──────│───────────────────▶│────── ClientChannel  │
│       (send)         │   (via socket)     │       (receive)      │
│                      │                    │                      │
│                      │   FinishSignal     │                      │
│  ServerChannel ◀─────│────────────────────│────── ClientChannel  │
│      (receive)       │   (via socket)     │        (send)        │
└──────────────────────┘                    └──────────────────────┘
```

### 5.2 窗口注册与InputChannel关联

当APP创建窗口时，会注册InputChannel:

```java
// ViewRootImpl.java
public void setView(View view, WindowManager.LayoutParams attrs, View panelParentView) {
    synchronized (this) {
        // 1. 创建InputChannel
        mInputChannel = new InputChannel();
        
        // 2. 添加窗口并传递InputChannel
        res = mWindowSession.addToDisplay(mWindow, mSeq, mWindowAttributes,
                getHostVisibility(), mDisplay.getDisplayId(), 
                mInputChannel, ...);
        
        // 3. 创建WindowInputEventReceiver
        if (mInputChannel != null) {
            mInputEventReceiver = new WindowInputEventReceiver(
                    mInputChannel, Looper.myLooper());
        }
    }
}
```

```java
// WindowManagerService端
// Session.java
public int addToDisplay(IWindow window, ..., InputChannel outInputChannel, ...) {
    return mService.addWindow(this, window, ..., outInputChannel, ...);
}

// WindowManagerService.java
public int addWindow(..., InputChannel outInputChannel, ...) {
    // 创建WindowState
    WindowState win = new WindowState(this, session, client, ...);
    
    // 打开InputChannel
    win.openInputChannel(outInputChannel);
    
    // 将Channel注册到InputDispatcher
    mInputManager.registerInputChannel(win.mInputChannel, win.mInputWindowHandle);
}
```

### 5.3 事件分发目标查找

#### 触摸事件目标查找

```cpp
// InputDispatcher.cpp
int32_t InputDispatcher::findTouchedWindowTargetsLocked(
        nsecs_t currentTime, 
        const MotionEntry& entry,
        std::vector<InputTarget>& inputTargets,
        TouchState& tempTouchState,
        bool* outConflictingPointerActions) {
    
    // 1. 获取显示器上的所有窗口
    const std::vector<sp<WindowInfoHandle>>& windowHandles = 
            getWindowHandlesLocked(displayId);
    
    // 2. 遍历窗口查找触摸目标
    for (const sp<WindowInfoHandle>& windowHandle : windowHandles) {
        const WindowInfo* windowInfo = windowHandle->getInfo();
        
        // 3. 判断触摸点是否在窗口范围内
        if (windowInfo->touchableRegionContainsPoint(x, y)) {
            
            // 4. 检查窗口是否可以接收输入
            if (canReceiveInput(*windowInfo)) {
                newTouchedWindowHandle = windowHandle;
                break;
            }
        }
    }
    
    // 5. 添加到输入目标列表
    addWindowTargetLocked(newTouchedWindowHandle, targetFlags, pointerIds, inputTargets);
    
    return injectionResult;
}
```

#### 焦点事件目标查找

```cpp
// InputDispatcher.cpp
int32_t InputDispatcher::findFocusedWindowTargetsLocked(
        nsecs_t currentTime,
        const EventEntry& entry,
        std::vector<InputTarget>& inputTargets,
        nsecs_t* outNextWakeupTime) {
    
    // 1. 获取当前焦点窗口
    sp<WindowInfoHandle> focusedWindowHandle = getFocusedWindowHandleLocked(displayId);
    
    // 2. 检查焦点窗口是否存在
    if (focusedWindowHandle == nullptr) {
        // 没有焦点窗口，可能需要等待
        if (mNoFocusedWindowTimeoutTime.has_value()) {
            // 检查超时
            if (currentTime > *mNoFocusedWindowTimeoutTime) {
                // 触发ANR
                onAnrLocked(mAwaitedFocusedApplication);
            }
        }
    }
    
    // 3. 添加焦点窗口为目标
    addWindowTargetLocked(focusedWindowHandle, InputTarget::FLAG_FOREGROUND,
                          BitSet32(0), inputTargets);
}
```

### 5.4 事件发送流程

```cpp
// InputDispatcher.cpp
void InputDispatcher::dispatchEventLocked(
        nsecs_t currentTime,
        EventEntry* eventEntry,
        const std::vector<InputTarget>& inputTargets) {
    
    for (const InputTarget& inputTarget : inputTargets) {
        // 1. 获取连接
        sp<Connection> connection = getConnectionLocked(inputTarget.inputChannel);
        
        // 2. 准备分发
        prepareDispatchCycleLocked(currentTime, connection, eventEntry, inputTarget);
    }
}

void InputDispatcher::startDispatchCycleLocked(
        nsecs_t currentTime, 
        const sp<Connection>& connection) {
    
    while (!connection->outboundQueue.empty()) {
        DispatchEntry* dispatchEntry = connection->outboundQueue.front();
        
        // 1. 发布事件到InputChannel
        status_t status = connection->inputPublisher.publishMotionEvent(...);
        
        if (status == OK) {
            // 2. 记录发送时间
            dispatchEntry->deliveryTime = currentTime;
            
            // 3. 移到等待队列
            connection->outboundQueue.dequeue(dispatchEntry);
            connection->waitQueue.push_back(dispatchEntry);
        }
    }
}
```

### 5.5 APP端事件接收与处理

```java
// ViewRootImpl.java
final class WindowInputEventReceiver extends InputEventReceiver {
    
    @Override
    public void onInputEvent(InputEvent event) {
        // 1. 判断事件类型，设置优先级
        int flags = 0;
        if (event instanceof MotionEvent && 
            event.getSource() == InputDevice.SOURCE_TOUCHSCREEN) {
            flags |= QueuedInputEvent.FLAG_RESYNTHESIZED;
        }
        
        // 2. 入队处理
        enqueueInputEvent(event, this, flags, true);
    }
    
    @Override
    public void onBatchedInputEventPending() {
        // 批量事件处理 - 用于优化连续触摸事件
        if (mUnbufferedInputDispatch) {
            super.onBatchedInputEventPending();
        } else {
            scheduleConsumeBatchedInput();
        }
    }
}

void enqueueInputEvent(InputEvent event, InputEventReceiver receiver, 
        int flags, boolean processImmediately) {
    
    // 1. 包装事件
    QueuedInputEvent q = obtainQueuedInputEvent(event, receiver, flags);
    
    // 2. 加入队列尾部
    QueuedInputEvent last = mPendingInputEventTail;
    if (last == null) {
        mPendingInputEventHead = q;
    } else {
        last.mNext = q;
    }
    mPendingInputEventTail = q;
    mPendingInputEventCount += 1;
    
    // 3. 立即处理或调度处理
    if (processImmediately) {
        doProcessInputEvents();
    } else {
        scheduleProcessInputEvents();
    }
}

void doProcessInputEvents() {
    while (mPendingInputEventHead != null) {
        QueuedInputEvent q = mPendingInputEventHead;
        mPendingInputEventHead = q.mNext;
        
        // 通过InputStage链分发
        deliverInputEvent(q);
    }
}
```

### 5.6 事件完成信号返回

```java
// InputEventReceiver.java
public final void finishInputEvent(InputEvent event, boolean handled) {
    if (event == null) {
        throw new IllegalArgumentException("event must not be null");
    }
    
    // 获取事件序列号
    int seq = mSeqMap.get(event, -1);
    if (seq != -1) {
        mSeqMap.delete(seq);
        // 通过JNI通知Native层
        nativeFinishInputEvent(mReceiverPtr, seq, handled);
    }
}
```

```cpp
// android_view_InputEventReceiver.cpp
static void nativeFinishInputEvent(JNIEnv* env, jclass clazz, jlong receiverPtr,
        jint seq, jboolean handled) {
    sp<NativeInputEventReceiver> receiver =
            reinterpret_cast<NativeInputEventReceiver*>(receiverPtr);
    
    // 发送完成信号到InputDispatcher
    status_t status = receiver->finishInputEvent(seq, handled);
}
```

---

## 六、常见Input ANR场景与优化

### 6.1 主线程阻塞

**问题**: 主线程执行耗时操作，无法及时处理输入事件

```java
// 错误示例
public void onClick(View v) {
    // 在主线程执行网络请求 - 可能导致ANR！
    String result = httpClient.get("https://api.example.com/data");
    textView.setText(result);
}

// 正确示例
public void onClick(View v) {
    new Thread(() -> {
        String result = httpClient.get("https://api.example.com/data");
        runOnUiThread(() -> textView.setText(result));
    }).start();
}
```

### 6.2 View层级过深

**问题**: 深层嵌套导致事件分发遍历耗时过长

```xml
<!-- 优化前 - 多层嵌套 -->
<LinearLayout>
    <LinearLayout>
        <LinearLayout>
            <LinearLayout>
                <TextView android:text="深层嵌套"/>
            </LinearLayout>
        </LinearLayout>
    </LinearLayout>
</LinearLayout>

<!-- 优化后 - 使用ConstraintLayout扁平化 -->
<ConstraintLayout>
    <TextView android:text="扁平布局"
        app:layout_constraintStart_toStartOf="parent"/>
</ConstraintLayout>
```

### 6.3 锁竞争

**问题**: 主线程等待锁，与其他线程竞争

```java
// 错误示例
private final Object lock = new Object();

public void onClick(View v) {
    synchronized(lock) {  // 可能等待其他线程释放锁
        // 处理点击
    }
}

// 正确示例 - 使用Handler机制避免锁竞争
private final Handler handler = new Handler(Looper.getMainLooper());

public void onClick(View v) {
    handler.post(() -> {
        // 在主线程顺序执行，无需锁
    });
}
```

### 6.4 频繁GC

**问题**: 大量对象创建导致频繁GC暂停

```java
// 错误示例 - 每次绘制都创建对象
@Override
protected void onDraw(Canvas canvas) {
    Paint paint = new Paint();  // 频繁创建！
    Rect rect = new Rect();     // 频繁创建！
    canvas.drawRect(rect, paint);
}

// 正确示例 - 复用对象
private final Paint mPaint = new Paint();
private final Rect mRect = new Rect();

@Override
protected void onDraw(Canvas canvas) {
    canvas.drawRect(mRect, mPaint);
}
```

---

## 七、调试与分析工具

### 7.1 dumpsys命令

```bash
# 查看InputDispatcher状态
adb shell dumpsys input

# 输出示例：
Input Dispatcher State:
  FocusedApplications:
    displayId=0, name='com.example.app/.MainActivity'
    
  FocusedWindows:
    displayId=0, name='com.example.app/com.example.app.MainActivity'
    
  AnrState:
    mNoFocusedWindowTimeoutTime: not set
    
  TouchStatesByDisplay:
    0: down=true, split=true
      Windows:
        TouchedWindow{name='...', pointerIds=0x00000001}
        
  Connections:
    Connection{name='...', status=NORMAL, outboundQueueLength=0, waitQueueLength=1}
```

### 7.2 systrace/perfetto分析

```bash
# 抓取input相关trace
python systrace.py -t 10 input view am wm -o trace.html

# 或使用perfetto
perfetto -c - --txt <<EOF
buffers: {
    size_kb: 63488
}
data_sources: {
    config {
        name: "linux.ftrace"
        ftrace_config {
            ftrace_events: "input"
            ftrace_events: "wm"
            ftrace_events: "am"
        }
    }
}
duration_ms: 10000
EOF
```

### 7.3 ANR日志分析

```
ANR in com.example.app
PID: 12345
Reason: Input dispatching timed out 
        (Waiting to send non-key event because the touched window 
         has not finished processing certain input events that were delivered 
         to it over 500.0ms ago.  Wait queue length: 3.  Wait queue head age: 5001.2ms.)
Load: 3.45 / 2.34 / 1.23
CPU usage from 10000ms to 0ms ago:
  45% 12345/com.example.app: 40% user + 5% kernel / faults: 1234 minor
  
----- pid 12345 at 2024-01-01 12:00:00 -----
"main" prio=5 tid=1 Sleeping
  | group="main" sCount=1 dsCount=0 obj=0x12345678 self=0xabcdef00
  | sysTid=12345 nice=0 cgrp=default sched=0/0 handle=0x12345678
  | state=S schedstat=( 123456789 12345678 1234 ) utm=100 stm=23 core=0 HZ=100
  | stack=0x12340000-0x12345000 stackSize=8MB
  at java.lang.Thread.sleep(Native Method)
  at com.example.app.MainActivity.onClick(MainActivity.java:42)  <-- 问题代码
```

---

## 八、总结

### 输入事件关键路径耗时参考

| 阶段 | 正常耗时 | 异常阈值 | 说明 |
|-----|---------|---------|------|
| 硬件→内核 | < 5ms | > 10ms | 驱动问题 |
| 内核→InputReader | < 10ms | > 50ms | EventHub阻塞 |
| InputReader→InputDispatcher | < 5ms | > 20ms | 处理积压 |
| InputDispatcher→InputChannel | < 5ms | > 50ms | 窗口查找/权限检查 |
| InputChannel→APP | < 5ms | > 50ms | 跨进程通信延迟 |
| APP事件处理 | < 16ms | > 100ms | **最常见瓶颈** |
| finish信号返回 | < 5ms | > 20ms | - |

### 最佳实践

1. **主线程轻量化**: 避免在主线程执行耗时操作
2. **布局扁平化**: 减少View层级嵌套
3. **对象池复用**: 减少GC频率
4. **异步处理**: 使用Handler、AsyncTask、协程等
5. **监控告警**: 集成ANR监控SDK，及时发现问题

---

## 参考资料

- [Android Source - InputReader.cpp](https://cs.android.com/android/platform/superproject/+/master:frameworks/native/services/inputflinger/reader/InputReader.cpp)
- [Android Source - InputDispatcher.cpp](https://cs.android.com/android/platform/superproject/+/master:frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp)
- [Android Source - ViewRootImpl.java](https://cs.android.com/android/platform/superproject/+/master:frameworks/base/core/java/android/view/ViewRootImpl.java)
- [Android Developer - ANR](https://developer.android.com/topic/performance/vitals/anr)
