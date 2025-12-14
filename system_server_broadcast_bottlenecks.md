# System_Server广播发送耗时点分析

## 概述
当system_server进程发送广播时，存在多个可能导致性能瓶颈的环节。本文档详细分析这些耗时点及其原因。

## 1. 广播队列处理阶段

### 1.1 广播入队操作
**位置**: `BroadcastQueue.enqueueBroadcastLocked()`

**可能的耗时点**:
- **广播去重检查**: 遍历现有的并行广播队列和串行广播队列，检查是否有重复的广播
- **IntentFilter匹配**: 需要遍历所有已注册的接收者，进行Intent匹配
- **权限检查**: 验证发送者是否有权限发送该广播，以及接收者是否有权限接收

**影响因素**:
- 队列中待处理的广播数量
- 系统中注册的BroadcastReceiver数量
- Intent的复杂度（action、category、data等）

### 1.2 接收者列表构建
**位置**: `BroadcastQueue.broadcastIntentLocked()`

**可能的耗时点**:
- **静态接收者查询**: 从PackageManagerService查询在AndroidManifest中声明的接收者
- **动态接收者查询**: 从IntentResolver中查询运行时注册的接收者
- **接收者排序**: 根据优先级对接收者进行排序
- **接收者去重**: 移除重复的接收者

**影响因素**:
- 系统中安装的应用数量
- 匹配该Intent的接收者数量
- 接收者的优先级分布

## 2. 接收者分发阶段

### 2.1 进程状态检查
**位置**: `BroadcastQueue.processCurBroadcastLocked()`

**可能的耗时点**:
- **进程查找**: 在ActivityManagerService中查找目标进程是否存在
- **进程状态评估**: 检查进程的优先级、OOM adj值等
- **进程启动等待**: 如果接收者进程未启动，需要等待进程启动完成

**影响因素**:
- 系统中运行的进程数量
- 进程启动速度（涉及zygote fork、应用初始化等）
- 系统内存压力

### 2.2 Binder事务处理
**位置**: `ApplicationThread.scheduleReceiver()`

**可能的耗时点**:
- **Binder缓冲区等待**: 如果Binder缓冲区满，需要等待
- **数据序列化**: Intent及其extras的序列化操作
- **跨进程传输**: Binder驱动的数据拷贝和传输
- **大数据传输**: Intent中携带的大型数据（如Bitmap）

**影响因素**:
- Binder缓冲区大小（通常为1MB）
- Intent中携带的数据大小
- 系统Binder通信负载

### 2.3 超时等待机制
**位置**: `BroadcastQueue.setBroadcastTimeoutLocked()`

**可能的耗时点**:
- **前台广播超时**: 默认10秒超时等待
- **后台广播超时**: 默认60秒超时等待
- **ANR处理**: 触发ANR后的日志收集和报告

**影响因素**:
- 接收者的onReceive()执行时间
- 接收者是否在主线程执行耗时操作
- 有序广播的串行特性

## 3. 有序广播特殊耗时点

### 3.1 串行执行特性
**位置**: `BroadcastQueue.processNextBroadcast()`

**可能的耗时点**:
- **逐个分发**: 必须等待当前接收者处理完成后才能分发给下一个
- **结果传递**: 每个接收者可能修改结果数据，需要传递给下一个接收者
- **中断处理**: 某个接收者可能中断广播，需要处理后续清理

**影响因素**:
- 接收者数量（线性增长）
- 每个接收者的处理时间
- 接收者链的总长度

### 3.2 结果等待
**位置**: `BroadcastQueue.finishReceiverLocked()`

**可能的耗时点**:
- **同步等待**: 发送者可能通过sendOrderedBroadcast()等待最终结果
- **结果回调**: 处理resultReceiver的回调

**影响因素**:
- 是否需要等待最终结果
- 接收者链的总处理时间

## 4. 系统级耗时点

### 4.1 锁竞争
**位置**: 多个synchronized块

**可能的耗时点**:
- **ActivityManagerService锁**: 全局锁，影响范围大
- **BroadcastQueue锁**: 广播队列锁，多线程发送广播时竞争
- **PackageManagerService锁**: 查询接收者时的锁竞争

**影响因素**:
- 系统并发活动数量
- 锁的持有时间
- 其他服务对相同锁的竞争

### 4.2 PackageManagerService查询
**位置**: `PackageManagerService.queryIntentReceivers()`

**可能的耗时点**:
- **Intent匹配计算**: 遍历所有已安装应用的IntentFilter
- **权限验证**: 检查组件的exported、permission等属性
- **缓存未命中**: 如果缓存失效，需要重新扫描package信息

**影响因素**:
- 已安装应用数量
- IntentFilter的复杂度
- PackageManagerService的缓存命中率

### 4.3 电源管理
**位置**: `PowerManager.WakeLock`

**可能的耗时点**:
- **WakeLock获取**: 对于需要唤醒设备的广播，需要持有WakeLock
- **Doze模式处理**: 在低电耗模式下，某些广播可能被延迟或限制
- **电源状态切换**: 唤醒设备的开销

**影响因素**:
- 设备当前电源状态（Doze、Idle等）
- 广播的重要性和紧急程度
- 系统电源策略

### 4.4 用户状态检查
**位置**: `BroadcastQueue.isUserRunning()`

**可能的耗时点**:
- **多用户状态查询**: 检查目标用户是否处于运行状态
- **用户切换等待**: 在用户切换过程中，某些广播可能需要等待
- **用户权限验证**: 验证跨用户广播的权限

**影响因素**:
- 设备上的用户数量
- 是否在进行用户切换
- 广播是否跨用户发送

## 5. 特定广播类型的耗时点

### 5.1 Sticky广播
**位置**: `ActivityManagerService.registerReceiver()`

**可能的耗时点**:
- **历史广播查找**: 查找并立即发送之前发送过的sticky广播
- **Sticky列表维护**: 维护系统的sticky广播列表

### 5.2 Protected广播
**位置**: `BroadcastQueue.verifyBroadcastLocked()`

**可能的耗时点**:
- **Protected验证**: 验证只有系统才能发送的protected广播
- **签名检查**: 验证发送者的签名和权限

### 5.3 系统广播
**位置**: 各种系统服务

**可能的耗时点**:
- **BOOT_COMPLETED**: 启动时大量应用同时响应
- **PACKAGE_ADDED/REMOVED**: 触发大量应用的更新逻辑
- **CONNECTIVITY_CHANGE**: 网络状态变化时的大量监听者

## 6. 优化建议

### 6.1 减少接收者数量
- 使用LocalBroadcastManager处理应用内广播
- 使用EventBus等替代方案
- 避免注册不必要的全局广播接收者

### 6.2 优化接收者实现
- onReceive()方法中避免耗时操作
- 使用goAsync()处理异步任务
- 避免在接收者中启动大量后台任务

### 6.3 合理使用广播类型
- 非必要不使用有序广播
- 避免频繁发送广播
- 考虑使用直接调用或Intent Service

### 6.4 系统级优化
- 监控Binder事务大小
- 优化PackageManagerService缓存
- 合理配置广播超时时间
- 使用广播队列分离（前台/后台）

## 7. 监控和诊断

### 7.1 关键日志
```
# 查看广播分发日志
adb logcat -s BroadcastQueue

# 查看ANR日志
adb logcat -s ActivityManager

# 查看Binder事务
adb logcat -s Binder
```

### 7.2 Systrace分析
```bash
# 捕获广播相关trace
python systrace.py -t 10 am pm dalvik sched freq idle load -b 32768
```

关键Trace点:
- `deliverToRegisteredReceiverLocked`
- `processCurBroadcastLocked`
- `broadcastIntentLocked`

### 7.3 Dumpsys命令
```bash
# 查看当前广播队列状态
adb shell dumpsys activity broadcasts

# 查看广播历史
adb shell dumpsys activity broadcasts history

# 查看pending广播
adb shell dumpsys activity broadcasts pending
```

## 8. 总结

System_server在广播发送过程中的主要耗时点包括：

1. **接收者匹配和查询** - O(n)复杂度，n为系统中的接收者数量
2. **Binder通信开销** - 受数据大小和系统负载影响
3. **有序广播的串行特性** - 线性累加所有接收者的处理时间
4. **锁竞争** - 特别是AMS全局锁
5. **进程启动等待** - 如果接收者进程未运行
6. **超时等待机制** - 最长可达60秒（后台广播）

理解这些耗时点对于优化Android系统性能和诊断广播相关问题至关重要。
