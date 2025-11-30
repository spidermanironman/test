# ANR问题分析报告

## ANR基本信息

**发生时间**: 11-24 17:33:51.566954  
**进程ID**: 19671  
**应用包名**: com.tencent.KiHan  
**ANR类型**: Input dispatching timed out  
**超时时间**: 5000ms (5秒)  
**问题窗口**: a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity  
**具体错误**: Waited 5000ms for FocusEvent(hasFocus=false)

## 问题场景还原

### 时间线分析

1. **17:33:44** - 用户第一次打开通知面板
   - 通知面板获得焦点：`Focus entering 892ff07 NotificationShade`
   - MainActivity失去焦点：`Focus leaving a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity, reason=Waiting for window because NOT_VISIBLE`

2. **17:33:45** - 用户关闭通知面板
   - 通知面板失去焦点：`Focus leaving 892ff07 NotificationShade`
   - MainActivity重新获得焦点：`Focus entering a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`

3. **17:33:46** - 用户再次快速打开通知面板
   - 通知面板再次获得焦点
   - MainActivity再次失去焦点

4. **17:33:47** - 用户再次关闭通知面板
   - 通知面板失去焦点：`Focus leaving 892ff07 NotificationShade, reason=NO_WINDOW`
   - 系统请求MainActivity获得焦点：`Focus request a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`
   - MainActivity应该获得焦点：`Focus entering a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`

5. **17:33:51** - ANR发生（约4秒后）
   - 系统等待MainActivity处理FocusEvent(hasFocus=false)超时

## 根本原因分析

### 1. 焦点事件处理超时
- 系统在17:33:47发送了FocusEvent(hasFocus=false)事件给MainActivity
- MainActivity的主线程在5秒内未能处理完该焦点事件
- 这违反了Android的响应时间要求（输入事件必须在5秒内处理完成）

### 2. 可能的原因

#### 主线程阻塞
- MainActivity的主线程可能正在执行耗时操作
- 可能的原因包括：
  - 同步网络请求
  - 大量数据计算
  - 文件I/O操作
  - 数据库查询
  - 复杂的UI渲染

#### 窗口状态恢复问题
- 从日志看，MainActivity经历了多次可见性变化：
  - `NOT_VISIBLE` → `focusable` → `NOT_VISIBLE` → `focusable`
- 在窗口重新可见时，可能执行了耗时的恢复操作：
  - 重新加载数据
  - 重新初始化视图
  - 重新绑定服务

#### 资源竞争
- 可能存在多个线程同时访问共享资源导致死锁或长时间等待

## 问题特征

1. **快速切换场景**: 用户在短时间内多次打开/关闭通知面板
2. **窗口状态频繁变化**: MainActivity在可见和不可见之间快速切换
3. **焦点事件堆积**: 多个焦点事件可能堆积在主线程消息队列中
4. **响应延迟**: 最后一次焦点切换后，应用未能及时响应

## 建议解决方案

### 1. 异步处理耗时操作
- 将网络请求、数据库操作移到后台线程
- 使用AsyncTask、Coroutines或RxJava处理异步任务

### 2. 优化窗口恢复逻辑
- 延迟加载非关键数据
- 使用缓存减少重复计算
- 避免在onResume()中执行耗时操作

### 3. 优化焦点事件处理
- 简化onWindowFocusChanged()方法
- 避免在焦点变化时执行复杂操作

### 4. 添加超时保护
- 对可能阻塞的操作添加超时机制
- 使用Handler.postDelayed()限制操作时间

### 5. 性能监控
- 添加ANR监控和上报
- 使用StrictMode检测主线程阻塞
- 使用Systrace分析性能瓶颈

## 相关日志关键点

```
17:33:44.759582 - Focus leaving MainActivity (第一次)
17:33:45.963488 - Focus entering MainActivity (第一次恢复)
17:33:46.490964 - Focus leaving MainActivity (第二次)
17:33:47.734992 - Focus entering MainActivity (第二次恢复，ANR前最后一次)
17:33:51.566954 - ANR发生（约4秒后）
```

## 结论

这是一个典型的**主线程阻塞导致的ANR问题**。MainActivity在处理窗口焦点恢复时，主线程被耗时操作阻塞，无法及时处理系统发送的FocusEvent事件，导致5秒超时触发ANR。

建议重点检查MainActivity的以下方法：
- `onWindowFocusChanged()`
- `onResume()`
- `onStart()`
- 以及任何可能在主线程中执行的初始化代码
