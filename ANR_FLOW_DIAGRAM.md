# ANR处理流程时序图

## 完整流程时序图

```
时间轴    系统层(AMS)              应用进程              守护线程
  │
T0  │  [ANR检测触发]
  │  │
T1  │  appNotResponding()
  │  │  ├─ 记录ANR信息
  │  │  ├─ 保存原始sigaction ─────────┐
  │  │  ├─ 设置新sigaction            │
  │  │  └─ 发送SIGQUIT ────────────────┼──→ [收到SIGQUIT]
  │  │                                  │
T2  │  [启动守护线程] ──────────────────┘
  │  │                                    │
  │  │                                    │  [等待10秒]
  │  │                                    │
T3  │                                    │  [执行handler]
  │  │                                    │  ├─ Dump堆栈
  │  │                                    │  ├─ 写入trace文件
  │  │                                    │  └─ notifyAnrHandled() ──→
  │  │                                    │                          │
T4  │  [接收回调] ←──────────────────────┘                          │
  │  │  ├─ 标记mAnrHandled=true                                      │
  │  │  └─ cancelMonitor() ──────────────────────────────────────────┘
  │  │                                    │
T5  │                                    │  [检查状态]
  │  │                                    │  ├─ 已处理 → 恢复sigaction
  │  │                                    │  └─ 未处理 → recoverFromAnr()
  │  │                                    │
T6  │  [恢复原始sigaction]                │
  │  │                                    │
  │  │  [流程完成]                        │
```

## 详细步骤分解

### 阶段1: ANR检测和初始化 (T0-T1)

```
┌─────────────────────────────────────────────────────────┐
│ 系统检测到ANR                                            │
│ - Input超时(5s)                                          │
│ - Broadcast超时(10s/60s)                                 │
│ - Service超时(20s)                                       │
│ - ContentProvider超时(10s)                              │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ ActivityManagerService.appNotResponding()               │
│                                                          │
│ 1. app.mErrorState.setAppNotResponding(annotation)      │
│ 2. 记录ANR时间: mAnrTime = SystemClock.uptimeMillis()   │
│ 3. 收集进程信息(pid, processName, componentName)        │
└─────────────────────────────────────────────────────────┘
```

### 阶段2: Signal准备和发送 (T1-T2)

```
┌─────────────────────────────────────────────────────────┐
│ Native层: prepare_signal_handling(pid)                  │
│                                                          │
│ 1. sigaction(SIGQUIT, NULL, &old_action)  // 保存原始  │
│ 2. 设置新handler: anr_signal_handler                    │
│ 3. sigaction(SIGQUIT, &new_action, NULL)                │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Process.sendSignal(pid, SIGNAL_QUIT)                    │
│                                                          │
│ Native: kill(pid, SIGQUIT)                              │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 应用进程收到SIGQUIT信号                                  │
│ (通过Linux信号机制传递)                                  │
└─────────────────────────────────────────────────────────┘
```

### 阶段3: 守护线程启动 (T2)

```
┌─────────────────────────────────────────────────────────┐
│ AnrHelper.appNotResponding()                            │
│                                                          │
│ AnrMonitorThread monitor = new AnrMonitorThread(app)    │
│ monitor.setDaemon(true)  // 守护线程                    │
│ monitor.start()                                         │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ AnrMonitorThread.run()                                  │
│                                                          │
│ Thread.sleep(10000)  // 等待10秒                        │
│                                                          │
│ 在等待期间:                                              │
│ - 如果应用响应 → cancel() → 恢复sigaction               │
│ - 如果超时 → recoverFromAnr()                          │
└─────────────────────────────────────────────────────────┘
```

### 阶段4: 应用处理Signal (T3)

```
┌─────────────────────────────────────────────────────────┐
│ 应用进程: anr_signal_handler(int sig)                   │
│                                                          │
│ if (sig == SIGQUIT) {                                   │
│   1. dump_all_thread_stacks(pid)                        │
│      ├─ 遍历 /proc/self/task/                           │
│      ├─ 读取每个线程的 /proc/self/task/{tid}/stack      │
│      └─ 写入 /data/anr/traces_{pid}.txt                 │
│                                                          │
│   2. notify_anr_handled(pid)                            │
│      └─ 通过Binder调用AMS.notifyAnrHandled()            │
│ }                                                        │
└─────────────────────────────────────────────────────────┘
```

### 阶段5: 系统接收回调 (T4)

```
┌─────────────────────────────────────────────────────────┐
│ ActivityManagerService.notifyAnrHandled(pid)            │
│                                                          │
│ synchronized (mPidsSelfLocked) {                        │
│   ProcessRecord app = mPidsSelfLocked.get(pid)         │
│   if (app != null) {                                    │
│     1. app.mErrorState.setAnrHandled()                  │
│        └─ mAnrHandled = true                            │
│                                                          │
│     2. mAnrHelper.cancelMonitor(app)                   │
│        └─ monitor.cancel()                             │
│           └─ mCancelled = true; interrupt()             │
│   }                                                      │
│ }                                                        │
└─────────────────────────────────────────────────────────┘
```

### 阶段6: 守护线程检查和恢复 (T5-T6)

```
┌─────────────────────────────────────────────────────────┐
│ AnrMonitorThread.run() (10秒后或被中断)                 │
│                                                          │
│ if (mCancelled || app.mErrorState.hasResponded()) {     │
│   // 应用已响应                                           │
│   restoreOriginalSigaction(app.pid)                     │
│   return                                                 │
│ } else {                                                 │
│   // 应用未响应                                           │
│   recoverFromAnr(app)                                    │
│ }                                                        │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ restoreOriginalSigaction(pid)                           │
│                                                          │
│ Native: restore_original_sigaction(pid)                 │
│   sigaction(SIGQUIT, &old_action, NULL)                 │
│                                                          │
│ 恢复应用原始的SIGQUIT处理方式                            │
└─────────────────────────────────────────────────────────┘
```

### 阶段7: 异常恢复 (如果应用未响应)

```
┌─────────────────────────────────────────────────────────┐
│ recoverFromAnr(ProcessRecord app)                       │
│                                                          │
│ 1. 再次发送SIGQUIT                                       │
│    Process.sendSignal(app.pid, SIGNAL_QUIT)            │
│    Thread.sleep(2000)                                   │
│                                                          │
│ 2. 检查进程是否存活                                      │
│    if (!isProcessAlive(app.pid)) return                 │
│                                                          │
│ 3. 强制恢复sigaction                                    │
│    restoreOriginalSigaction(app.pid)                    │
│                                                          │
│ 4. 根据策略决定是否kill                                  │
│    if (shouldKillProcess(app)) {                        │
│       app.kill("ANR timeout", true)                     │
│    }                                                     │
└─────────────────────────────────────────────────────────┘
```

## 关键时间点

| 时间点 | 事件 | 说明 |
|--------|------|------|
| T0 | ANR检测 | 系统检测到应用无响应 |
| T1 | appNotResponding() | 开始ANR处理流程 |
| T1.5 | 保存/设置sigaction | 准备信号处理 |
| T2 | 发送SIGQUIT | 触发应用dump堆栈 |
| T2.5 | 启动守护线程 | 10秒倒计时开始 |
| T3 | 应用处理信号 | Dump堆栈并通知系统 |
| T4 | 系统接收回调 | 标记ANR已处理 |
| T5 | 守护线程检查 | 检查处理状态 |
| T6 | 恢复sigaction | 恢复原始信号处理 |

## 10秒恢复机制原理

```
┌─────────────────────────────────────────────────────────┐
│ 为什么需要10秒恢复机制？                                 │
│                                                          │
│ 1. 防止信号handler被永久替换                            │
│    - 应用可能有自己的SIGQUIT处理逻辑                    │
│    - 临时替换handler仅用于ANR处理                       │
│                                                          │
│ 2. 处理应用无法响应的情况                               │
│    - 如果应用深度阻塞，可能无法处理SIGQUIT              │
│    - 10秒后强制恢复，避免系统状态不一致                 │
│                                                          │
│ 3. 资源保护                                              │
│    - 确保信号处理机制的正常运行                         │
│    - 防止ANR处理影响应用的正常运行                      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ 恢复机制的工作流程                                       │
│                                                          │
│ 正常情况:                                                │
│  应用响应(通常<1秒) → 立即恢复sigaction                  │
│                                                          │
│ 异常情况:                                                │
│  应用未响应(>10秒) → 强制恢复sigaction                  │
│                      → 可选kill进程                      │
└─────────────────────────────────────────────────────────┘
```

## 数据流图

```
ANR检测
  │
  ├─→ ProcessRecord.mErrorState
  │      ├─ mAppNotResponding = true
  │      ├─ mAnrTime = now
  │      └─ mAnrHandled = false
  │
  ├─→ Native层
  │      ├─ 保存原始sigaction → g_original_sigquit_action
  │      └─ 设置新sigaction → anr_signal_handler
  │
  ├─→ 发送SIGQUIT
  │      └─→ 应用进程
  │             ├─ 执行handler
  │             ├─ Dump堆栈 → /data/anr/traces_{pid}.txt
  │             └─ 通知系统 → Binder回调
  │
  └─→ 守护线程
         ├─ 等待10秒
         ├─ 检查mAnrHandled状态
         └─ 恢复sigaction
```

## 状态转换图

```
[正常状态]
    │
    │ ANR检测
    ↓
[ANR状态]
    │
    ├─→ [保存sigaction] → [设置新sigaction] → [发送SIGQUIT]
    │
    ├─→ [启动守护线程] → [等待10秒]
    │
    └─→ [应用处理]
            │
            ├─→ [通知系统] → [标记已处理] → [恢复sigaction] → [正常状态]
            │
            └─→ [超时未处理] → [强制恢复] → [可选kill] → [进程终止]
```
