# 输入事件分发时间点分析

## 日志时间线分析

### 关键时间点

| 时间戳 | 事件 | 说明 |
|--------|------|------|
| 17:33:47.734775 | NFW_setFocusedWindow | 设置焦点窗口到 `com.tencent.KiHan/com.tencent.KiHan.MainActivity` |
| 17:33:47.734803 | updateFocusedWindow | 更新焦点窗口（延迟: 0.028ms） |
| 17:33:47.734847 | currInputWindows | 当前输入窗口列表更新（延迟: 0.044ms） |
| 17:33:47.735026 | publishFocusEvent | 发布焦点事件到应用（延迟: 0.179ms） |
| 17:33:49.491109 | dumpPreTrace | ANR预追踪开始（延迟: 1.756秒） |
| 17:33:49.492257 | getThreadGroupLeader | 获取线程组leader（延迟: 1.148ms） |
| 17:33:49.496236 | preAnr notify | ANR预通知（延迟: 3.979ms） |
| 17:33:51.491934 | ANR确认 | 应用无响应确认（延迟: 1.996秒） |

## 详细分析

### 1. 焦点窗口设置阶段 (17:33:47.734775 - 17:33:47.735026)

**时间跨度: 0.251ms**

- **17:33:47.734775**: `NFW_setFocusedWindow` - InputDispatcher 设置焦点窗口
  - 窗口: `a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`
  - Display: 0
  - 与之前窗口相同: false (same as the previous:0)

- **17:33:47.734803**: `updateFocusedWindow` - 更新焦点窗口状态
  - 原因: setFocusedWindow
  - 延迟: 0.028ms

- **17:33:47.734847**: `currInputWindows` - 更新当前输入窗口列表
  - 包含多个窗口（NavigationBar, StatusBar, Notification Barrage Window等）
  - 延迟: 0.044ms

- **17:33:47.735026**: `publishFocusEvent` - **关键时间点：事件发布到应用**
  - Channel: `a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`
  - hasFocus: true
  - **这是输入事件分发到应用的时刻**
  - 延迟: 0.179ms（从窗口设置到事件发布）

### 2. ANR检测阶段 (17:33:49.491109 - 17:33:51.491934)

**时间跨度: 2.001秒**

- **17:33:49.491109**: `dumpPreTrace` - ANR预追踪开始
  - PID: 19671
  - **距离焦点事件发布: 1.756秒**
  - 说明：应用在1.756秒内未响应输入事件

- **17:33:49.492257**: `getThreadGroupLeader` - 获取线程组信息
  - PID: 19671
  - TGID: 19671
  - 延迟: 1.148ms

- **17:33:49.496236**: `preAnr notify` - ANR预通知
  - UID: 10370
  - 检查冻结状态
  - 延迟: 3.979ms

- **17:33:51.491934**: `onAnrLocked` - **ANR确认**
  - 窗口: `a1e7783 com.tencent.KiHan/com.tencent.KiHan.MainActivity`
  - Sequence: 24937847
  - **距离焦点事件发布: 3.757秒**
  - **距离ANR预追踪: 2.001秒**

## 关键发现

### 1. 输入事件分发延迟
- **焦点窗口设置到事件发布**: 0.251ms（非常快，正常）
- InputDispatcher 内部处理效率很高

### 2. 应用响应延迟
- **事件发布到ANR预追踪**: 1.756秒
- **事件发布到ANR确认**: 3.757秒
- Android 默认ANR超时为5秒（KeyDispatchTimeout），但这里在3.757秒就确认了ANR

### 3. ANR检测流程
1. 输入事件发布到应用 (17:33:47.735026)
2. 等待应用响应（超时检测）
3. ANR预追踪开始 (17:33:49.491109) - 约1.76秒后
4. ANR确认 (17:33:51.491934) - 约3.76秒后

### 4. 可能的问题
- 应用主线程阻塞，无法处理输入事件
- Sequence 24937847 对应的输入事件未能及时处理
- 应用可能在执行耗时操作（数据库查询、网络请求、复杂计算等）

## 建议

1. **检查应用主线程**：查看是否有耗时操作阻塞主线程
2. **检查输入事件处理**：确认应用是否正确处理了焦点事件和输入事件
3. **性能分析**：使用 Traceview 或 Systrace 分析应用在17:33:47.735026到17:33:49.491109之间的执行情况
4. **日志分析**：查看应用日志，确认是否有异常或错误导致主线程阻塞
