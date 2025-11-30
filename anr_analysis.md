# ANR问题分析报告

## ANR基本信息

**发生时间**: 11-24 17:33:51.566954  
**应用包名**: com.tencent.KiHan  
**进程ID**: 19671  
**ANR类型**: Input dispatching timed out (输入分发超时)  
**等待时间**: 5000ms  
**等待事件**: FocusEvent(hasFocus=false)

## 问题场景还原

### 时间线分析

1. **17:33:44** - 用户下拉通知栏
   - NotificationShade获得焦点
   - MainActivity失去焦点（reason=Waiting for window because NOT_VISIBLE）

2. **17:33:45** - 用户关闭通知栏
   - NotificationShade失去焦点
   - MainActivity重新获得焦点（reason=setFocusedWindow）

3. **17:33:46** - 用户再次下拉通知栏
   - NotificationShade再次获得焦点
   - MainActivity再次失去焦点

4. **17:33:47** - 用户关闭通知栏
   - 17:33:47.719129 - NotificationShade失去焦点（reason=NO_WINDOW）
   - 17:33:47.720790 - 系统请求MainActivity获得焦点（reason=UpdateInputWindows）
   - 17:33:47.734992 - MainActivity成功获得焦点（reason=setFocusedWindow）

5. **17:33:51** - ANR发生
   - 距离上次焦点事件约4秒后，系统检测到ANR

## 根本原因分析

### 1. 输入事件处理超时
- **ANR类型**: Input dispatching timed out
- **等待事件**: FocusEvent(hasFocus=false)
- 系统等待MainActivity处理焦点丢失事件超过5秒

### 2. 可能的原因

#### 主要原因：主线程阻塞
从日志时间线看，MainActivity在17:33:47成功获得焦点后，可能在处理某些耗时操作导致主线程阻塞：

1. **UI渲染阻塞**
   - MainActivity重新可见后需要重新绘制UI
   - 可能存在复杂的布局计算或视图渲染

2. **同步操作**
   - 在主线程执行了网络请求、数据库操作、文件IO等耗时操作
   - 阻塞了输入事件的处理

3. **死锁或无限循环**
   - 主线程可能陷入死锁或无限循环
   - 导致无法响应系统事件

### 3. 触发场景
- **用户操作**: 快速打开/关闭通知栏
- **焦点切换**: MainActivity在可见/不可见状态间频繁切换
- **系统行为**: 每次焦点切换都会触发FocusEvent，需要应用及时处理

## 问题定位建议

### 1. 检查主线程堆栈
需要查看ANR发生时的主线程堆栈，定位具体阻塞位置：
```
adb shell dumpsys dropbox --print | grep -A 30 "anr"
```

### 2. 检查应用代码
- 检查MainActivity的`onWindowFocusChanged()`方法
- 检查`onResume()`、`onPause()`等生命周期方法
- 检查是否有在主线程执行的耗时操作

### 3. 性能监控
- 使用Systrace或Perfetto分析主线程耗时
- 检查是否有过度绘制或布局性能问题

## 解决方案建议

### 1. 异步处理耗时操作
- 将网络请求、数据库操作移到后台线程
- 使用协程或线程池处理异步任务

### 2. 优化UI渲染
- 减少布局层级
- 使用ViewStub延迟加载
- 优化自定义View的绘制逻辑

### 3. 优化焦点处理
- 简化`onWindowFocusChanged()`中的逻辑
- 避免在焦点变化时执行耗时操作

### 4. 添加超时保护
- 对可能阻塞的操作添加超时机制
- 使用Handler.postDelayed()限制执行时间

## 总结

这是一个典型的**主线程阻塞导致的输入事件处理超时ANR**。应用在通知栏关闭后重新获得焦点时，主线程被阻塞超过5秒，无法及时处理系统的FocusEvent，导致ANR发生。

**关键问题**: MainActivity的主线程在17:33:47获得焦点后，执行了耗时操作，阻塞了后续输入事件的处理。

**解决方向**: 需要将主线程中的耗时操作移到后台线程，优化UI渲染性能，确保输入事件能够及时响应。
