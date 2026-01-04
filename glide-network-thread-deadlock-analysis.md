# Glide 网络线程死锁导致 ANR 分析

## 问题概述

**问题时间**: 2026-01-01 13:00:58  
**应用**: com.weico.international  
**ANR 类型**: Input dispatching timed out (5000ms)

## 根本原因

这是一个典型的 **锁竞争 + 阻塞网络操作** 导致的死锁 ANR。

### 死锁链条

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              死锁示意图                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   主线程 (main, tid=1)                 glide-source-thread-3 (tid=240)      │
│   ┌──────────────────┐                 ┌──────────────────────────────┐     │
│   │ Activity.onStop  │                 │ SingleRequest.onLoadFailed   │     │
│   │       ↓          │                 │ (持有锁 <0x06574aeb>)         │     │
│   │ RequestManager   │                 │           ↓                  │     │
│   │ .pauseRequests() │                 │ MyGlideListener.onLoadFailed │     │
│   │       ↓          │                 │           ↓                  │     │
│   │ SingleRequest    │  ══等待锁══>    │ DownstreamLog.fire()         │     │
│   │ .isRunning()     │                 │           ↓                  │     │
│   │ (等待 <0x06574aeb>)│                │ ILog.fillDNS()               │     │
│   └──────────────────┘                 │           ↓                  │     │
│                                        │ getaddrinfo() ← 阻塞在DNS查询 │     │
│                                        └──────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 详细堆栈分析

### 1. 主线程 (Blocked)

主线程正在处理 Activity 的 `onStop` 生命周期回调：

```
Activity.performStop()
  → ReportFragment.onActivityPreStopped()
    → LifecycleRegistry.handleLifecycleEvent()
      → RequestManager.onStop()
        → RequestManager.pauseRequests()
          → RequestTracker.pauseRequests()
            → SingleRequest.isRunning()  ← 在这里等待锁
```

**关键信息**:
- `waiting to lock <0x06574aeb>` - 等待获取对象锁
- `held by thread 240` - 锁被 tid=240 的线程持有

### 2. glide-source-thread-3 (tid=240, Native)

这个线程持有锁 `<0x06574aeb>`，但卡在 native 层的 DNS 查询：

```
SingleRequest.onLoadFailed()     ← 持有锁 <0x06574aeb>
  → MyGlideListener.onLoadFailed()
    → DownstreamLog.fire()
      → ILog.fire()
        → AbsAddLogBatch.addLog()
          → AddLogBatchImpl._addLog()
            → ILog.preUpload()
              → ILog.fillDNS()
                → Dns.lookup()
                  → InetAddress.getAllByName()
                    → android_getaddrinfo()  ← 阻塞在这里
```

**关键信息**:
- `locked <0x06574aeb>` - 持有对象锁
- 卡在 `android_getaddrinfo_proxy` 的 `read` 系统调用
- DNS 查询可能因为网络问题长时间阻塞

## 问题代码定位

### 问题 1: Glide 回调中执行同步网络操作

**文件**: `ImageLoader.kt` (第 847 行)
```kotlin
class MyGlideListener : ... {
    override fun onLoadFailed(...) {
        // 问题代码：在 Glide 回调中同步执行网络操作
        DownstreamLog.fire(...)  // 这会触发 DNS 查询
    }
}
```

### 问题 2: 日志上报包含阻塞的 DNS 查询

**文件**: `ILog.kt` (第 57 行)
```kotlin
fun fillDNS(...) {
    // 问题代码：同步执行 DNS 查询
    InetAddress.getAllByName(host)  // 这是阻塞调用
}
```

## 根因总结

| 层级 | 问题 | 严重程度 |
|------|------|----------|
| 应用层 | 在 Glide 回调中执行同步网络操作 | 🔴 严重 |
| 应用层 | 日志上报逻辑包含阻塞的 DNS 查询 | 🔴 严重 |
| Glide 库 | 在持有锁的情况下调用外部回调 | 🟡 设计缺陷 |

## 修复建议

### 方案 1: 异步化日志上报 (推荐)

```kotlin
// ILog.kt
class ILog {
    private val logExecutor = Executors.newSingleThreadExecutor()
    
    fun fire(data: LogData) {
        // 将日志上报操作移到后台线程
        logExecutor.execute {
            preUpload(data)
            // ... 实际上报逻辑
        }
    }
}
```

### 方案 2: 移除 DNS 预填充或异步化

```kotlin
// ILog.kt
fun preUpload(data: LogData) {
    // 选项 A: 完全移除 DNS 预填充（让 OkHttp 自己处理）
    // fillDNS(...)  // 删除这行
    
    // 选项 B: 使用异步 DNS 查询
    scope.launch(Dispatchers.IO) {
        fillDNS(...)
    }
}
```

### 方案 3: 避免在 Glide 回调中执行耗时操作

```kotlin
// ImageLoader.kt
class MyGlideListener : ... {
    private val logScope = CoroutineScope(Dispatchers.IO)
    
    override fun onLoadFailed(...) {
        // 异步执行日志上报
        logScope.launch {
            DownstreamLog.fire(...)
        }
    }
}
```

### 方案 4: 设置 DNS 查询超时

```kotlin
// 如果必须同步执行 DNS，至少设置超时
fun fillDNS(host: String) {
    try {
        withTimeout(1000) {  // 1秒超时
            InetAddress.getAllByName(host)
        }
    } catch (e: TimeoutException) {
        // 超时后跳过 DNS 预填充
    }
}
```

## 为什么 DNS 查询会长时间阻塞？

1. **网络切换**: 用户可能正在 WiFi 和移动网络之间切换
2. **DNS 服务器问题**: DNS 服务器响应慢或不可达
3. **代理设置**: 系统代理可能导致 DNS 查询通过 proxy
4. **运营商劫持**: 某些运营商的 DNS 可能有延迟

从堆栈可以看到 `android_getaddrinfo_proxy`，说明 DNS 查询走的是 Android 的 DNS 代理机制，这在某些情况下会有额外延迟。

## 验证方法

1. **复现**: 在弱网或断网环境下触发图片加载失败，然后快速切换 Activity
2. **监控**: 添加 DNS 查询耗时监控
3. **日志**: 在关键锁操作前后添加日志追踪

## 优先级评估

| 指标 | 评估 |
|------|------|
| 影响范围 | 所有使用 Glide 加载图片的场景 |
| 触发条件 | 图片加载失败 + Activity 生命周期切换 + 网络慢 |
| 严重程度 | 高 - 直接导致 ANR |
| 修复难度 | 低 - 只需异步化日志上报 |
| 建议优先级 | P0 - 尽快修复 |

## 结论

这是一个由于在 Glide 回调中同步执行网络操作（DNS 查询）导致的死锁 ANR。**最简单有效的修复方案是将 `DownstreamLog.fire()` 的调用改为异步执行**，避免在 Glide 持有锁的回调中执行任何可能阻塞的操作。
