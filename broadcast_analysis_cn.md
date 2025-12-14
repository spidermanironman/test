# System Server 广播发送耗时点分析

在 Android 的 `system_server` 进程中，广播的发送和分发是一个复杂的过程，涉及多个系统服务。以下是可能导致耗时的关键点：

## 1. AMS 入口与锁竞争 (Sending Phase)
- **Global Lock / AMS Lock**: 调用 `ActivityManagerService.broadcastIntent` 时，通常需要获取 AMS 锁。如果系统负载高，AMS 锁竞争激烈，会导致发送广播的请求被阻塞。
- **权限检查 (Permission Checks)**: 系统需要校验发送者和接收者的权限，涉及与 `PermissionManager` 的交互，复杂的权限逻辑可能带来耗时。

## 2. 接收者查找与解析 (Receiver Resolution)
- **PMS 查询 (`queryIntentReceivers`)**: 这是常见的性能瓶颈。AMS 需要通过 `PackageManagerService` (PMS) 查找所有匹配该 Intent 的静态注册接收者（Manifest Receivers）。
  - 如果安装的应用非常多，或者 PMS 正在处理其他事务（如应用安装/更新），此步骤会很慢。
  - 涉及大量 XML 解析或缓存查找。
- **Flag 过滤**: 处理 `FLAG_EXCLUDE_STOPPED_PACKAGES` 等标志位，需要过滤掉处于停止状态的应用。

## 3. 队列管理 (BroadcastQueue)
- **入队操作**: 将广播记录 (BroadcastRecord) 插入到后台或前台广播队列。
- **有序广播阻塞 (Ordered Broadcasts)**: 对于有序广播，队列必须等待前一个接收者处理完毕 (`onReceive`) 并返回结果后，才能分发给下一个。如果某个接收者处理缓慢，会直接阻塞整个队列的分发。

## 4. 广播分发 (Dispatching Phase)
- **进程启动 (Cold Start)**: **这是最大的耗时点**。如果静态注册的接收者所在进程未运行，AMS 必须先启动该进程 (`startProcessLocked`)。
  - 进程创建涉及 Zygote fork、资源加载、Application 初始化等，耗时通常在几十到几百毫秒甚至更多。
  - 如果广播触发了大量进程启动（"广播风暴"），会导致 CPU 飙升和系统卡顿。
- **Binder IPC**: 将广播分发给已运行的进程需要进行 Binder 调用 (`IApplicationThread.scheduleReceiver`)。
  - 如果目标应用的主线程卡死或繁忙，Binder 调用可能会阻塞或超时。
  - 大量并发的 Binder 通信可能导致 Binder 驱动负载过高。
- **OOM Adj 更新**: AMS 需要更新接收者进程的优先级 (OOM Adjustment)，防止其被杀，这涉及复杂的计算。

## 5. 系统监控与策略
- **ANR 计时器**: 系统需要为有序广播设置超时监测。
- **Power Management**: 如果广播涉及唤醒设备，会与 PowerManagerService 交互。

## 总结：最常见的性能瓶颈
1. **冷启动进程**: 广播唤起大量未运行的进程。
2. **AMS/PMS 锁竞争**: 高负载下的锁等待。
3. **有序广播阻塞**: 单个应用处理慢拖累整个队列。
4. **PMS 查询慢**: 应用安装数量巨大时，查找接收者耗时增加。
