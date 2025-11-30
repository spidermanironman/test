# ANR分析报告

## ANR基本信息

**时间**: 11-24 17:33:51.566954  
**应用**: com.tencent.KiHan  
**Activity**: com.tencent.KiHan.MainActivity  
**窗口ID**: a1e7783  
**ANR类型**: Input dispatching timed out  
**等待时间**: 5000ms  
**等待事件**: FocusEvent(hasFocus=false)

## 问题场景

从日志分析，这是一个典型的**窗口焦点切换导致的输入分发超时**问题。

### 时间线分析

1. **17:33:44.759** - MainActivity失去焦点
   - 原因：`Waiting for window because NOT_VISIBLE`
   - 此时通知栏（NotificationShade）正在展开

2. **17:33:44.798** - NotificationShade获得焦点
   - 原因：`Window became focusable. Previous reason: NOT_VISIBLE`

3. **17:33:45.963** - 通知栏关闭，焦点切换回MainActivity
   - Focus leaving NotificationShade: `setFocusedWindow`
   - Focus entering MainActivity: `setFocusedWindow`

4. **17:33:46.320** - 用户再次点击状态栏
   - `input_interaction: Interaction with: 70fa60d StatusBar`

5. **17:33:46.490** - MainActivity再次失去焦点
   - 原因：`Waiting for window because NOT_VISIBLE`
   - 通知栏再次展开

6. **17:33:46.581** - NotificationShade获得焦点

7. **17:33:47.691** - 通知栏关闭
   - `notification_panel_hidden`

8. **17:33:47.719** - NotificationShade失去焦点
   - 原因：`NO_WINDOW`

9. **17:33:47.720** - 系统请求MainActivity获得焦点
   - `Focus request a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`

10. **17:33:47.734** - MainActivity获得焦点
    - `Focus entering MainActivity, reason=setFocusedWindow`

11. **17:33:51.566** - **ANR发生**
    - 等待FocusEvent(hasFocus=false)超时5000ms

## 根本原因分析

### 1. 窗口可见性问题
- MainActivity在通知栏展开时被标记为`NOT_VISIBLE`
- 当通知栏关闭后，系统尝试恢复MainActivity的焦点
- 但MainActivity可能没有及时响应窗口可见性变化

### 2. 焦点事件处理延迟
- 系统发送了`FocusEvent(hasFocus=false)`事件
- MainActivity的主线程在5秒内没有处理完这个焦点事件
- 导致输入分发超时

### 3. 可能的原因
- **主线程阻塞**：MainActivity的主线程可能被其他操作阻塞（如：
  - 同步I/O操作
  - 复杂的UI渲染
  - 数据库操作
  - 网络请求（虽然不应该在主线程）
  - 死锁或长时间运行的代码）

- **窗口状态恢复慢**：Activity在从不可见恢复到可见状态时，可能执行了耗时的操作

- **View绘制问题**：从日志中可以看到多次`viewroot_draw_event`，可能存在绘制性能问题

## 建议的解决方案

1. **检查主线程阻塞**
   - 使用StrictMode检测主线程的I/O操作
   - 检查是否有同步网络请求
   - 检查数据库操作是否在主线程

2. **优化窗口生命周期处理**
   - 在`onWindowFocusChanged()`中避免耗时操作
   - 确保窗口可见性变化时快速响应

3. **异步处理**
   - 将耗时操作移到后台线程
   - 使用协程或异步任务处理非UI操作

4. **性能优化**
   - 优化View绘制性能
   - 减少不必要的布局计算
   - 使用ViewStub延迟加载

5. **添加监控**
   - 添加ANR监控和上报
   - 记录主线程的耗时操作

## 关键日志片段

```
17:33:47.720790  3392  3733 I input_focus: [Focus request a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity,reason=UpdateInputWindows]
17:33:47.734992  3392  5341 I input_focus: [Focus entering a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity,reason=setFocusedWindow]
17:33:51.566954  3392 18315 I am_anr  : [0,19671,com.tencent.KiHan,988298820,Input dispatching timed out (a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity is not responding. Waited 5000ms for FocusEvent(hasFocus=false)).]
```

从焦点恢复到ANR发生，间隔约3.8秒，说明MainActivity在获得焦点后，处理`FocusEvent(hasFocus=false)`时发生了阻塞。
