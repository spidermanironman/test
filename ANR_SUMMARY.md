# ANR处理流程快速参考

## 核心流程（一句话总结）

**ANR检测 → 保存原始sigaction → 设置新sigaction → 发送SIGQUIT → 启动10秒守护线程 → 应用dump堆栈 → 通知系统 → 恢复原始sigaction**

## 关键步骤

### 1. 入口点
- **方法**: `ActivityManagerService.processErrorState().appNotResponding()`
- **位置**: `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java`

### 2. Signal处理
- **Signal类型**: SIGQUIT (Signal 3)
- **发送方式**: `Process.sendSignal(pid, Process.SIGNAL_QUIT)`
- **Native实现**: `kill(pid, SIGQUIT)`

### 3. 守护线程
- **类名**: `AnrMonitorThread`
- **超时时间**: 10秒 (`ANR_TIMEOUT_MS = 10000`)
- **作用**: 监控ANR处理状态，超时后恢复sigaction

### 4. 应用处理
- **Handler**: `anr_signal_handler(int sig)`
- **操作**: Dump所有线程堆栈到 `/data/anr/traces_{pid}.txt`
- **回调**: `Process.notifyAnrHandled(pid)` → `AMS.notifyAnrHandled(pid)`

### 5. 恢复机制
- **时机**: 应用响应后立即恢复，或10秒后强制恢复
- **方法**: `restoreOriginalSigaction(pid)`
- **Native**: `sigaction(SIGQUIT, &old_action, NULL)`

## 10秒恢复机制原理

### 为什么需要？

1. **防止信号handler被永久替换**
   - 应用可能有自己的SIGQUIT处理逻辑
   - 临时替换仅用于ANR处理

2. **处理应用无法响应的情况**
   - 如果应用深度阻塞（如死锁），可能无法处理SIGQUIT
   - 10秒后强制恢复，避免系统状态不一致

3. **资源保护**
   - 确保信号处理机制正常运行
   - 防止ANR处理影响应用正常运行

### 工作流程

```
发送SIGQUIT前:
  1. 保存原始sigaction → g_original_sigquit_action
  2. 设置新sigaction → anr_signal_handler

发送SIGQUIT后:
  启动守护线程，等待10秒

10秒内应用响应:
  → 立即恢复原始sigaction
  → 取消守护线程

10秒内应用未响应:
  → 强制恢复原始sigaction
  → 可选kill进程
```

## 关键代码位置

| 功能 | 文件路径 |
|------|----------|
| ANR入口 | `frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java` |
| ANR处理 | `frameworks/base/services/core/java/com/android/server/am/AnrHelper.java` |
| Signal发送 | `frameworks/base/core/jni/android_util_Process.cpp` |
| Signal处理 | `frameworks/base/core/jni/AndroidRuntime.cpp` |
| 进程管理 | `frameworks/base/core/java/android/os/Process.java` |

## 关键数据结构

```java
ProcessRecord.mErrorState {
    boolean mAppNotResponding      // ANR状态标志
    String mAppNotRespondingReport // ANR报告
    long mAnrTime                  // ANR发生时间
    boolean mAnrHandled            // 是否已处理
    int mAnrCount                  // ANR次数
}
```

## 时序要点

| 时间 | 事件 |
|------|------|
| T0 | ANR检测触发 |
| T1 | appNotResponding()调用 |
| T1.5 | 保存/设置sigaction |
| T2 | 发送SIGQUIT，启动守护线程 |
| T3 | 应用处理信号，dump堆栈 |
| T4 | 应用通知系统已处理 |
| T5 | 守护线程检查状态 |
| T6 | 恢复原始sigaction |

## 异常处理

### 应用无法响应SIGQUIT
- **检测**: 守护线程10秒超时
- **处理**: 强制恢复sigaction，可选kill进程

### 进程已死亡
- **检测**: `isProcessAlive(pid)`
- **处理**: 清理资源，记录ANR事件

### 多次ANR
- **策略**: ANR次数 > 3 → 强制kill进程
- **例外**: 系统进程不kill，但记录日志

## 相关文档

- **详细流程**: `ANR_FLOW_EXPLANATION.md`
- **代码细节**: `ANR_CODE_DETAILS.md`
- **流程图**: `ANR_FLOW_DIAGRAM.md`

## 快速查找

### 查找ANR相关代码
```bash
# 查找appNotResponding方法
grep -r "appNotResponding" frameworks/base/services/core/java/com/android/server/am/

# 查找SIGQUIT处理
grep -r "SIGQUIT\|SIGNAL_QUIT" frameworks/base/core/jni/

# 查找守护线程
grep -r "AnrMonitorThread\|ANR_TIMEOUT" frameworks/base/services/core/java/com/android/server/am/
```

### 查看ANR Trace文件
```bash
# 查看最新的ANR trace
adb shell cat /data/anr/traces.txt

# 查看特定进程的trace
adb shell cat /data/anr/traces_<pid>.txt
```
