# ANR问题分析报告

## ANR错误信息
```
am_anr: [0,19671,com.tencent.KiHan,988298820,Input dispatching timed out 
(a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity is not responding. 
Waited 5000ms for FocusEvent(hasFocus=false)).]
```

## 问题场景还原

### 时间线分析

**17:33:44** - 用户下拉通知栏
- 通知面板（NotificationShade）打开
- 焦点从游戏应用 `com.tencent.KiHan` 转移到通知面板
- 日志：`Focus leaving a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`
- 日志：`Focus entering 892ff07 NotificationShade`

**17:33:45** - 用户关闭通知栏
- 通知面板关闭
- 系统尝试将焦点返回到游戏应用
- 日志：`Focus entering a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity,reason=setFocusedWindow`

**17:33:46** - 用户再次下拉通知栏
- 通知面板再次打开
- 焦点再次离开游戏应用

**17:33:47** - 用户再次关闭通知栏
- 通知面板关闭
- 系统再次尝试将焦点返回到游戏应用
- 日志：`Focus entering a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity,reason=setFocusedWindow`

**17:33:51** - ANR发生（约4秒后）
- 系统等待游戏应用处理 `FocusEvent(hasFocus=false)` 事件超时
- 等待时间：5000ms（5秒）

## ANR根本原因

### 1. 输入事件分发超时
- **错误类型**：`Input dispatching timed out`
- **具体事件**：`FocusEvent(hasFocus=false)` - 窗口失去焦点事件
- **超时时间**：5000ms（5秒）

### 2. 应用主线程阻塞
游戏应用 `com.tencent.KiHan` 的主线程在处理窗口焦点变化事件时：
- 无法在5秒内响应系统发送的焦点事件
- 主线程可能被以下操作阻塞：
  * 同步I/O操作（文件读写、网络请求）
  * 耗时计算
  * 死锁或线程竞争
  * 大量UI渲染操作
  * 数据库操作

### 3. 触发场景
- 用户在游戏过程中频繁操作通知栏
- 每次通知栏关闭时，系统都会发送焦点事件给游戏应用
- 游戏应用在处理这些焦点事件时响应缓慢

## 问题特征

1. **窗口焦点管理问题**：应用在窗口可见性变化时处理不当
   - `View.INVISIBLE` 状态下的处理逻辑可能存在问题
   - 焦点恢复时的初始化操作可能耗时过长

2. **资源竞争**：可能存在线程同步问题
   - 主线程等待其他线程完成操作
   - 锁竞争导致主线程阻塞

3. **内存压力**：可能存在内存泄漏或GC压力
   - 大量对象创建导致频繁GC
   - GC暂停时间过长影响主线程响应

## 建议解决方案

### 1. 代码层面
- 检查 `onWindowFocusChanged()` 方法的实现
- 将耗时操作移到后台线程
- 优化焦点恢复时的初始化逻辑
- 检查是否有死锁或线程阻塞问题

### 2. 性能优化
- 使用异步操作处理I/O和网络请求
- 优化UI渲染性能
- 减少主线程上的同步操作

### 3. 监控和调试
- 使用Systrace分析主线程阻塞原因
- 检查是否有内存泄漏
- 监控GC频率和耗时

## 总结

这是一个典型的**输入事件分发超时ANR**，发生在用户频繁操作通知栏导致窗口焦点频繁切换的场景下。游戏应用的主线程在处理窗口失去焦点事件时响应超时，导致系统判定应用无响应。根本原因是应用主线程被阻塞，无法及时处理系统发送的焦点事件。
