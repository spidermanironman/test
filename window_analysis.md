# 窗口焦点问题分析

## ANR信息
- **时间点**: 12-02 18:08:49.155
- **进程**: com.ss.android.ugc.aweme (PID: 26768)
- **ANR原因**: `Input dispatching timed out (Application does not have a focused window)`
- **超时时间**: 949501508ms (约10秒)

## 问题分析

### 关键时间线

| 时间 | 事件 | 窗口状态 |
|------|------|----------|
| 18:08:48.260 | StatusBar窗口显示完成 | READY_TO_SHOW → HAS_DRAWN |
| 18:08:48.438 | NavigationBar窗口显示完成 | READY_TO_SHOW → HAS_DRAWN |
| **18:08:49.155** | **ANR发生** | **应用没有focused window** |
| 18:08:49.247 | Splash Screen窗口显示完成 | READY_TO_SHOW → HAS_DRAWN |
| 18:08:51.973 | Camera窗口被销毁 | DRAW_PENDING → NO_SURFACE |

### 根本原因

**问题**: 在ANR发生时（18:08:49.155），应用的Splash Screen窗口还没有完成绘制和显示（完成于18:08:49.247），导致应用没有获得焦点的窗口。

**时间差**: ANR发生在Splash Screen窗口显示完成之前约92毫秒。

### 窗口状态转换分析

#### Splash Screen窗口 (Window{40e1fee})
```
18:08:49.239: DRAW_PENDING → COMMIT_DRAW_PENDING (finishDrawingLocked)
18:08:49.243: COMMIT_DRAW_PENDING → READY_TO_SHOW (commitFinishDrawingLocked)
18:08:49.247: READY_TO_SHOW → HAS_DRAWN (performShowLocked)
```

**问题**: 窗口绘制流程正常，但完成时间晚于ANR发生时间。

### 可能的原因

1. **窗口绘制延迟**
   - Splash Screen窗口的绘制过程耗时较长
   - 从DRAW_PENDING到HAS_DRAWN耗时约8ms，但可能在更早的阶段就存在延迟

2. **窗口焦点获取时机问题**
   - 应用可能在窗口完全显示（HAS_DRAWN）之前就尝试获取焦点
   - 系统在窗口未完全显示时不会授予焦点

3. **主线程阻塞**
   - 虽然窗口绘制在系统进程中，但应用主线程可能在等待窗口显示完成
   - 主线程阻塞导致无法及时响应输入事件

4. **窗口层级问题**
   - 可能存在其他窗口遮挡或影响焦点获取
   - Camera窗口的存在可能影响焦点分配

### 建议的解决方案

1. **优化启动流程**
   - 确保Splash Screen窗口尽早创建和显示
   - 减少启动时的主线程阻塞操作

2. **窗口焦点管理**
   - 在窗口完全显示（HAS_DRAWN）后再请求焦点
   - 使用`WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE`临时标记，显示完成后再移除

3. **输入事件处理**
   - 在窗口未获得焦点时，延迟处理输入事件
   - 使用`onWindowFocusChanged()`回调确保窗口已获得焦点

4. **性能优化**
   - 减少Splash Screen的绘制复杂度
   - 优化窗口创建和显示流程

### 相关窗口状态

- **StatusBar**: 正常显示（18:08:48.260）
- **NavigationBar**: 正常显示（18:08:48.438）
- **Splash Screen**: 显示延迟，导致ANR
- **ScreenDecorOverlay**: 正常显示（18:08:49.447）
- **Camera窗口**: 在ANR后2.8秒被销毁（可能相关）

### 结论

这是一个典型的窗口焦点时序问题。应用在窗口完全显示并获得焦点之前就尝试处理输入事件，导致系统判定为ANR。需要优化窗口显示流程，确保在窗口完全显示后再处理用户输入。
