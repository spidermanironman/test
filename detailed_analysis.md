# 输入事件分发时间点详细分析

## 日志上下文

```
行 272238: 11-24 17:33:47.734775  3392  6976 I InputDispatcher: NFW_setFocusedWindow, a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity on display 0, same as the previous:0
行 272239: 11-24 17:33:47.734803  3392  6976 I InputDispatcher: updateFocusedWindow, a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity on display 0, reason: setFocusedWindow, result:   FocusedWindows:
行 272242: 11-24 17:33:47.734847  3392  6976 V InputDispatcher: currInputWindows displayId=0 {e845aa NavigationBar_displayId_0,0,id=85,ownerPid=6633,iC=0x104,a=1.00,tR=<empty>} {70fa60d StatusBar,0,id=96,ownerPid=6633,iC=0x104,a=1.00,tR=[1131,0][1272,2772]} {6a8710 New Notification Barrage Window2,0,id=6387,ownerPid=9677,i ...
行 272243: 11-24 17:33:47.735026  3392  5341 V InputDispatcher: channel 'a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity' ~  publishFocusEvent(hasFocus=true)
行 272525: 11-24 17:33:49.491109  3392  5341 I InputDispatcherExtImpl: dumpPreTrace: pid = 19671
行 272526: 11-24 17:33:49.492257  3392  5341 I InputDispatcherExtImpl: getThreadGroupLeader, pid 19671, return tgid 19671
行 272527: 11-24 17:33:49.496236  3392  5341 D OplusActivityManagerServiceEnhance: InputDispatcher preAnr notify hans to check uid 10370 frozen state
行 272784: 11-24 17:33:51.491934  3392  5341 I InputDispatcher: AnrLogEnhancement:onAnrLocked a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity is not responding seq=24937847
```

## 时间点分析

### 关键时间点：输入事件分发到应用

**时间戳**: `17:33:47.735026`  
**事件**: `publishFocusEvent(hasFocus=true)`  
**Channel**: `a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`

这是**输入事件分发到应用的精确时间点**。此时InputDispatcher通过InputChannel将焦点事件发布到应用的InputEventReceiver。

## 时间线分解

### 阶段1：InputDispatcher内部处理（0.251ms）

| 时间 | 事件 | 线程 | 说明 | 延迟 |
|------|------|------|------|------|
| 17:33:47.734775 | NFW_setFocusedWindow | 6976 | 设置焦点窗口 | - |
| 17:33:47.734803 | updateFocusedWindow | 6976 | 更新焦点窗口状态 | 0.028ms |
| 17:33:47.734847 | currInputWindows | 6976 | 更新输入窗口列表 | 0.044ms |
| 17:33:47.735026 | publishFocusEvent | 5341 | **事件发布到应用** ⭐ | 0.179ms |

**分析**：
- InputDispatcher内部处理非常高效，总耗时仅0.251ms
- 注意线程切换：6976 → 5341（可能是不同的InputDispatcher线程）

### 阶段2：应用响应等待（1.756秒）

| 时间 | 事件 | 线程 | 说明 | 距离事件发布 |
|------|------|------|------|-------------|
| 17:33:47.735026 | publishFocusEvent | 5341 | 事件发布到应用 | 0ms |
| 17:33:49.491109 | dumpPreTrace | 5341 | ANR预追踪开始 | **1.756秒** |

**分析**：
- 应用在1.756秒内未响应输入事件
- Android默认KeyDispatchTimeout为5秒，但这里提前触发了ANR检测

### 阶段3：ANR检测流程（2.001秒）

| 时间 | 事件 | 线程 | 说明 | 延迟 |
|------|------|------|------|------|
| 17:33:49.491109 | dumpPreTrace | 5341 | ANR预追踪，PID=19671 | - |
| 17:33:49.492257 | getThreadGroupLeader | 5341 | 获取TGID=19671 | 1.148ms |
| 17:33:49.496236 | preAnr notify | 5341 | ANR预通知，UID=10370 | 3.979ms |
| 17:33:51.491934 | onAnrLocked | 5341 | ANR确认，seq=24937847 | 1.996秒 |

**分析**：
- ANR预追踪到确认耗时2.001秒
- Sequence 24937847 对应的输入事件未能及时处理

## 技术细节

### 1. InputDispatcher线程

- **线程6976**: 处理窗口焦点设置（NFW_setFocusedWindow, updateFocusedWindow）
- **线程5341**: 处理事件分发和ANR检测（publishFocusEvent, dumpPreTrace）

### 2. 窗口信息

- **窗口Token**: `a1e7783`
- **应用**: `com.tencent.KiHan/com.tencent.KiHan.MainActivity`
- **Display**: 0
- **Sequence**: 24937847（ANR时的事件序列号）

### 3. 进程信息

- **PID**: 19671（ANR检测时的进程ID）
- **TGID**: 19671（线程组ID）
- **UID**: 10370（用户ID）

### 4. ANR检测机制

1. **预追踪阶段**（dumpPreTrace）：收集进程信息
2. **预通知阶段**（preAnr notify）：通知HANS（华为/OPPO的ANR处理系统）检查冻结状态
3. **确认阶段**（onAnrLocked）：确认ANR并记录日志

## 性能指标总结

| 指标 | 时间 | 状态 |
|------|------|------|
| InputDispatcher处理延迟 | 0.251ms | ✅ 正常 |
| 应用响应超时 | 1.756秒 | ❌ 异常 |
| ANR确认时间 | 3.757秒 | ❌ 异常 |
| ANR检测耗时 | 2.001秒 | ✅ 正常 |

## 问题诊断

### 可能的原因

1. **主线程阻塞**
   - 执行耗时操作（数据库查询、文件I/O、网络请求）
   - 同步等待其他线程
   - 死锁或死循环

2. **输入事件处理异常**
   - 事件处理回调中执行耗时操作
   - 事件队列积压
   - 焦点事件处理逻辑问题

3. **系统资源问题**
   - CPU占用过高
   - 内存不足
   - I/O阻塞

### 诊断建议

1. **查看应用日志**
   ```bash
   adb logcat | grep -i "KiHan\|19671"
   ```

2. **使用Traceview分析**
   ```bash
   # 在ANR发生前后抓取trace
   adb shell am trace-ipc start
   # ... 等待ANR ...
   adb shell am trace-ipc stop
   ```

3. **检查主线程堆栈**
   - 查看ANR日志中的主线程堆栈
   - 确认阻塞点

4. **性能分析**
   - 使用Systrace分析系统级性能
   - 使用Android Profiler分析应用性能

## 结论

**输入事件分发时间点**: `17:33:47.735026`（publishFocusEvent）

**关键发现**：
- InputDispatcher在0.251ms内完成事件分发，性能正常
- 应用在1.756秒内未响应，导致ANR预追踪
- 最终在3.757秒后确认ANR

**建议**：重点检查应用主线程在事件发布后的执行情况，找出阻塞原因。
