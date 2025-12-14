# System Server 广播发送耗时点分析

## 概述
System Server 进程在发送广播时可能存在的性能瓶颈和耗时点分析。

## 主要耗时点

### 1. 广播队列管理
- **队列锁竞争**
  - `BroadcastQueue` 的锁竞争，特别是 `mQueue` 锁
  - 多个广播同时发送时的锁等待
  - 队列满时的阻塞等待

- **队列遍历和匹配**
  - 遍历所有注册的 `BroadcastReceiver`
  - 根据 Intent 的 action、category、data 等进行匹配
  - 权限检查（`checkComponentPermission`）

### 2. 接收者查找和过滤
- **静态接收者查询**
  - 查询 PackageManager 获取静态注册的接收者
  - 解析 AndroidManifest.xml 中的 `<receiver>` 标签
  - 权限验证（`checkComponentPermission`）

- **动态接收者查找**
  - 遍历 `mReceiverResolver`（IntentResolver）
  - Intent 匹配算法（`IntentFilter` 匹配）
  - 权限检查

- **用户过滤**
  - 多用户场景下的用户过滤
  - `queryIntentReceivers` 的用户过滤逻辑

### 3. 权限检查
- **组件权限检查**
  - `checkComponentPermission` 调用
  - 跨进程权限检查的开销

- **广播权限检查**
  - `checkBroadcastPermission` 验证发送者权限
  - `checkReceiverPermission` 验证接收者权限
  - 权限查询可能涉及 Binder 调用

### 4. 进程启动和调度
- **目标进程未运行**
  - 启动目标应用进程（`startProcessLocked`）
  - 进程启动的延迟（fork、zygote 通信等）
  - ActivityManagerService 的进程管理开销

- **进程优先级调整**
  - `setProcessImportant` 调整进程优先级
  - OOM 调整器的工作

- **进程调度延迟**
  - 目标进程处于后台时的调度延迟
  - 系统负载高时的调度延迟

### 5. Binder 通信开销
- **跨进程通信**
  - 每个接收者的 Binder 调用
  - `scheduleReceiver` 的 Binder 传输
  - 序列化 Intent 数据（Parcel）

- **Binder 线程池竞争**
  - Binder 线程池满时的等待
  - 大量并发广播时的线程竞争

### 6. 广播队列处理
- **串行化处理**
  - `processNextBroadcast` 的串行执行
  - 前一个广播未完成时，后续广播的等待

- **超时处理**
  - `BROADCAST_TIMEOUT` 检查
  - 超时广播的清理和日志记录

### 7. 系统广播的特殊处理
- **系统广播优化**
  - 系统广播的特殊路径（如 BOOT_COMPLETED）
  - 大量接收者的批量处理

- **粘性广播处理**
  - 粘性广播的存储和恢复
  - `stickyBroadcasts` 的维护

### 8. 日志和统计
- **日志记录**
  - `Slog` 日志输出
  - 广播统计信息的更新
  - Trace 日志记录

### 9. 内存和GC压力
- **对象创建**
  - Intent、BroadcastRecord 等对象的创建
  - 大量接收者时的内存分配

- **GC 暂停**
  - 频繁对象创建导致的 GC
  - 系统负载高时的 GC 暂停

### 10. 锁竞争和同步
- **AMS 锁竞争**
  - `ActivityManagerService` 的全局锁
  - `mBroadcastQueues` 的锁竞争

- **PackageManager 锁**
  - 查询接收者时的 PackageManager 锁
  - 包信息缓存的锁竞争

## 性能优化建议

### 1. 减少不必要的广播
- 避免频繁发送广播
- 使用 LocalBroadcastManager 替代系统广播（已废弃，可用其他方式）

### 2. 优化接收者数量
- 减少静态注册的接收者
- 合并多个接收者的功能

### 3. 异步处理
- 使用 `sendBroadcast` 的异步版本
- 避免在广播接收者中执行耗时操作

### 4. 权限优化
- 减少不必要的权限检查
- 使用更细粒度的权限

### 5. 队列优化
- 调整广播队列大小
- 优化队列处理逻辑

## 关键代码路径

### BroadcastQueue.processNextBroadcast()
主要的广播处理逻辑，包含：
- 队列遍历
- 接收者匹配
- 权限检查
- 进程启动
- Binder 调用

### ActivityManagerService.broadcastIntent()
广播发送的入口点，包含：
- 权限验证
- 队列选择
- 接收者查询

### IntentResolver.queryIntent()
接收者匹配的核心算法

## 监控和诊断

### 关键指标
- 广播发送延迟
- 队列长度
- 接收者数量
- 进程启动时间
- Binder 调用耗时

### 工具
- `dumpsys activity broadcasts`
- `systrace` / `perfetto`
- `am broadcast` 命令
- Trace 日志分析
