# AMS 处理应用进程死亡（BinderDied）的完整流程

## 1. 概述

当应用进程挂掉（crash、被 kill、ANR 等）后，AMS 通过 BinderDied 机制感知到进程死亡，并执行一系列清理和通知操作。

## 2. 整体流程图

```
应用进程死亡
     |
     v
+--------------------+
|   Binder 驱动      |  检测到进程退出，发送 BR_DEAD_BINDER
+--------------------+
     |
     v
+--------------------+
| AppDeathRecipient  |  binderDied() 回调被触发
|   .binderDied()    |
+--------------------+
     |
     v
+--------------------+
|    appDiedLocked() |  AMS 核心死亡处理入口
+--------------------+
     |
     +---> handleAppDiedLocked()      清理 ProcessRecord
     |
     +---> cleanUpApplicationRecord() 清理应用记录
     |         |
     |         +---> 清理 Service
     |         +---> 清理 ContentProvider
     |         +---> 清理 BroadcastReceiver
     |         +---> 通知 WMS 清理窗口
     |
     +---> 处理 Activity 栈
     |         |
     |         +---> 清理 Activity 记录
     |         +---> 恢复/重建 Activity
     |
     +---> 是否需要重启进程？
               |
               +---> 重启 persistent 应用
               +---> 重启有待处理任务的应用
```

## 3. 注册死亡监听

### 3.1 应用进程启动时注册

当应用进程启动并 attach 到 AMS 时，AMS 会注册死亡监听：

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

private boolean attachApplicationLocked(IApplicationThread thread,
        int pid, int callingUid, long startSeq) {
    
    ProcessRecord app;
    // 根据 pid 找到对应的 ProcessRecord
    if (pid != MY_PID && pid >= 0) {
        synchronized (mPidsSelfLocked) {
            app = mPidsSelfLocked.get(pid);
        }
    }
    
    // ... 省略其他初始化 ...
    
    // 关键：注册死亡通知
    try {
        // 创建 AppDeathRecipient
        AppDeathRecipient adr = new AppDeathRecipient(app, pid, thread);
        // 注册 linkToDeath
        thread.asBinder().linkToDeath(adr, 0);
        app.deathRecipient = adr;
    } catch (RemoteException e) {
        // 如果注册失败，说明进程可能已经死了
        app.resetPackageList(mProcessStats);
        mProcessList.startProcessLocked(app, 
            new HostingRecord("link fail", processName));
        return false;
    }
    
    // ... 继续其他初始化 ...
}
```

### 3.2 AppDeathRecipient 类

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

private final class AppDeathRecipient implements IBinder.DeathRecipient {
    final ProcessRecord mApp;
    final int mPid;
    final IApplicationThread mAppThread;

    AppDeathRecipient(ProcessRecord app, int pid,
            IApplicationThread thread) {
        mApp = app;
        mPid = pid;
        mAppThread = thread;
    }

    @Override
    public void binderDied() {
        if (DEBUG_ALL) Slog.v(TAG,
                "Death received in " + this
                + " for thread " + mAppThread.asBinder());
        
        synchronized(ActivityManagerService.this) {
            // 核心：调用 appDiedLocked 处理进程死亡
            appDiedLocked(mApp, mPid, mAppThread, true, null);
        }
    }
}
```

## 4. appDiedLocked：核心入口

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

final void appDiedLocked(ProcessRecord app, int pid, IApplicationThread thread,
        boolean fromBinderDied, String reason) {
    
    // 检查 ProcessRecord 是否匹配
    // 防止处理已经被复用的 pid
    if (app.pid != pid || app.thread != thread) {
        // 旧进程的死亡通知，忽略
        return;
    }
    
    // 记录进程死亡原因
    boolean doLowMem = app.getActiveInstrumentation() == null;
    boolean doOomAdj = doLowMem;
    
    if (!app.killed) {
        // 非预期死亡（crash）
        if (!fromBinderDied) {
            // 如果不是从 binderDied 来的，可能是信号导致的死亡
            killProcessQuiet(pid);
            killProcessGroup(app.uid, pid);
        }
        
        // 记录 crash 信息
        reportProcessDiedLocked(app);
    }
    
    // 核心处理
    handleAppDiedLocked(app, false, true);
    
    // 内存不足时通知其他进程
    if (doLowMem) {
        doLowMemReportIfNeededLocked(app);
    }
}
```

## 5. handleAppDiedLocked：清理处理

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

private void handleAppDiedLocked(ProcessRecord app,
        boolean restarting, boolean allowRestart) {
    
    int pid = app.pid;
    
    // ========== 1. 清理应用记录 ==========
    boolean kept = cleanUpApplicationRecordLocked(app, restarting, 
                                                   allowRestart, -1, false);
    
    // ========== 2. 从进程列表中移除 ==========
    if (!kept && !restarting) {
        removeLruProcessLocked(app);
        if (pid > 0) {
            ProcessList.remove(pid);
        }
    }
    
    // ========== 3. 处理 Activity ==========
    // 通知 ActivityTaskManagerService 处理 Activity 清理
    if (mAtmInternal != null) {
        mAtmInternal.handleAppDied(app.getWindowProcessController(), 
                                    restarting, () -> {
            // 回调：更新 OOM adj
            updateOomAdjLocked(OomAdjuster.OOM_ADJ_REASON_PROCESS_END);
        });
    }
    
    // ========== 4. 更新进程优先级 ==========
    if (!restarting && !app.killedByAm) {
        updateOomAdjLocked(OomAdjuster.OOM_ADJ_REASON_PROCESS_END);
    }
}
```

## 6. cleanUpApplicationRecordLocked：详细清理

这是最核心的清理函数，负责清理进程相关的所有组件：

```java
// frameworks/base/services/core/java/com/android/server/am/ActivityManagerService.java

final boolean cleanUpApplicationRecordLocked(ProcessRecord app,
        boolean restarting, boolean allowRestart, int index,
        boolean replacingPid) {
    
    // ========== 1. 清理 Service ==========
    mServices.killServicesLocked(app, allowRestart);
    
    // ========== 2. 清理 ContentProvider ==========
    // 2.1 清理该进程发布的 Provider
    boolean restart = false;
    for (int i = app.pubProviders.size() - 1; i >= 0; i--) {
        ContentProviderRecord cpr = app.pubProviders.valueAt(i);
        
        // 检查是否有客户端还在使用
        final boolean alwaysRemove = app.bad || !allowRestart;
        final boolean inLaunching = removeDyingProviderLocked(app, cpr, alwaysRemove);
        
        if (!alwaysRemove && inLaunching && cpr.hasConnectionOrHandle()) {
            // 有客户端在等待，需要重启进程
            restart = true;
        }
        
        cpr.provider = null;
        cpr.setProcess(null);
    }
    app.pubProviders.clear();
    
    // 2.2 清理该进程使用的外部 Provider 连接
    for (int i = app.conProviders.size() - 1; i >= 0; i--) {
        ContentProviderConnection conn = app.conProviders.get(i);
        conn.provider.connections.remove(conn);
        // 通知 Provider 所在进程：连接已断开
        stopAssociationLocked(app.uid, app.processName, 
                              conn.provider.uid, 
                              conn.provider.appInfo.longVersionCode,
                              conn.provider.name);
    }
    app.conProviders.clear();
    
    // ========== 3. 清理 BroadcastReceiver ==========
    skipCurrentReceiverLocked(app);
    
    // 清理该进程注册的动态广播接收器
    for (int i = app.receivers.size() - 1; i >= 0; i--) {
        removeReceiverLocked(app.receivers.valueAt(i));
    }
    app.receivers.clear();
    
    // ========== 4. 清理 Backup ==========
    if (mBackupTargets.get(app.userId) == app) {
        mBackupTargets.delete(app.userId);
        mHandler.post(() -> {
            // 通知 BackupManager 代理停止
            mBackupAgents.get(app.userId)
                .agentDisconnected(app.info.packageName);
        });
    }
    
    // ========== 5. 通知 WMS 清理窗口 ==========
    // WindowProcessController 会清理该进程的所有窗口
    app.getWindowProcessController().onCleanupApplicationRecord();
    
    // ========== 6. 清理其他资源 ==========
    // 清理 alarm
    mBatteryStatsService.noteProcessFinish(app.processName, app.info.uid);
    
    // 清理 wakelock
    if (app.pid > 0 && app.pid != MY_PID) {
        mBatteryStatsService.noteProcessDied(app.pid, 
                                              app.processStateDependentRecords);
    }
    
    // 清理 notification
    mAppOpsService.unregisterCallbackForPid(app.pid);
    
    // ========== 7. 决定是否重启 ==========
    if (!app.isPersistent() || app.isolated) {
        // 非 persistent 应用，从进程列表移除
        mProcessList.removeProcessLocked(app, false, false, "clean up");
        return false;
    }
    
    if (restart) {
        // 需要重启（如有 Provider 客户端在等待）
        mProcessList.startProcessLocked(app, 
            new HostingRecord("restart", app.processName));
    }
    
    return true; // kept
}
```

## 7. Service 清理：killServicesLocked

```java
// frameworks/base/services/core/java/com/android/server/am/ActiveServices.java

final void killServicesLocked(ProcessRecord app, boolean allowRestart) {
    
    // ========== 1. 处理该进程运行的 Service ==========
    for (int i = app.numberOfRunningServices() - 1; i >= 0; i--) {
        ServiceRecord sr = app.getRunningServiceAt(i);
        
        // 停止前台通知
        if (sr.isForeground) {
            sr.postNotification();
            sr.cancelNotification();
        }
        
        // 标记为已被 kill
        sr.setProcess(null, null, 0, null);
        sr.isolatedProc = null;
        
        // 处理绑定连接
        for (int j = sr.bindings.size() - 1; j >= 0; j--) {
            IntentBindRecord b = sr.bindings.valueAt(j);
            
            // 通知所有客户端：Service 已断开
            for (int k = b.apps.size() - 1; k >= 0; k--) {
                ProcessRecord client = b.apps.valueAt(k).client;
                if (client != null && client.thread != null) {
                    try {
                        // 关键：通知客户端 onServiceDisconnected
                        client.thread.scheduleUnbindService(
                            sr, b.intent.getIntent());
                    } catch (Exception e) {
                        // 客户端可能也死了
                    }
                }
            }
        }
        
        // 判断是否需要重启
        if (allowRestart && sr.crashCount < MAX_SERVICE_CRASHES 
                && (sr.serviceInfo.applicationInfo.flags 
                    & ApplicationInfo.FLAG_PERSISTENT) != 0) {
            // Persistent Service 需要重启
            scheduleServiceRestartLocked(sr, true);
        } else {
            // 彻底停止 Service
            bringDownServiceLocked(sr);
        }
    }
    
    // ========== 2. 处理该进程绑定的远程 Service ==========
    for (int i = app.connections.size() - 1; i >= 0; i--) {
        ConnectionRecord c = app.connections.valueAt(i);
        // 移除绑定
        removeConnectionLocked(c, app, null);
    }
    app.connections.clear();
}
```

## 8. Activity 清理处理

```java
// frameworks/base/services/core/java/com/android/server/wm/ActivityTaskManagerService.java

void handleAppDied(WindowProcessController wpc, boolean restarting,
        Runnable finishInstrumentCallback) {
    
    synchronized (mGlobalLock) {
        // 遍历所有 Activity 栈
        mRootWindowContainer.forAllActivities((r) -> {
            if (r.app == wpc) {
                // 该 Activity 属于死亡的进程
                
                if (r.isVisible()) {
                    // 可见 Activity，标记为需要重建
                    r.notifyAppDied();
                }
                
                // 清理 Activity 状态
                r.setState(DESTROYED, "handleAppDied");
                r.app = null;
                
                // 如果是栈顶 Activity，需要恢复下一个
                if (r == mFocusedActivity) {
                    clearFocusedActivity(r);
                }
            }
        });
        
        // 清理进程的 Activity 列表
        wpc.clearActivities();
        
        // 恢复栈顶 Activity
        if (!restarting) {
            mRootWindowContainer.resumeFocusedStacksTopActivities();
        }
    }
}
```

## 9. 进程重启逻辑

AMS 在以下情况会重启进程：

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessList.java

boolean shouldRestartProcess(ProcessRecord app) {
    
    // 1. Persistent 应用必须重启
    if (app.isPersistent()) {
        return true;
    }
    
    // 2. 有正在启动的 Activity
    if (app.pendingStart) {
        return true;
    }
    
    // 3. 有需要重启的 Service
    if (mAm.mServices.hasServiceNeedRestart(app)) {
        return true;
    }
    
    // 4. 有客户端正在等待 ContentProvider
    if (hasWaitingProvider(app)) {
        return true;
    }
    
    // 5. 有待处理的 Broadcast
    if (hasPendingBroadcast(app)) {
        return true;
    }
    
    return false;
}

// 重启进程
void startProcessLocked(ProcessRecord app, HostingRecord hostingRecord) {
    // 重置状态
    app.pid = 0;
    app.setStartSeq(0);
    
    // 延迟重启（避免频繁 crash 导致死循环）
    long delay = getProcessStartDelay(app);
    if (delay > 0) {
        mHandler.sendMessageDelayed(
            mHandler.obtainMessage(START_PROCESS_MSG, app),
            delay);
        return;
    }
    
    // 立即启动
    startProcessLocked(app, hostingRecord, 0, 0, null);
}
```

## 10. 完整时序图

```
应用进程                  Binder驱动                    AMS
    |                        |                          |
    X 进程死亡               |                          |
    |                        |                          |
    |   BR_DEAD_BINDER       |                          |
    |----------------------->|                          |
                             |  binderDied()            |
                             |------------------------->|
                             |                          |
                             |            appDiedLocked()
                             |                 |
                             |                 v
                             |        handleAppDiedLocked()
                             |                 |
                             |                 v
                             |   +-------------+-------------+
                             |   |             |             |
                             |   v             v             v
                             | 清理         清理          清理
                             | Service      Provider      Activity
                             |   |             |             |
                             |   v             v             v
                             | 通知客户端   通知客户端    恢复栈顶
                             | unbind       disconnected  Activity
                             |   |             |             |
                             |   +-------------+-------------+
                             |                 |
                             |                 v
                             |          是否需要重启？
                             |                 |
                             |       +---------+---------+
                             |       | Yes               | No
                             |       v                   v
                             |  startProcess()      移除进程记录
                             |       |
                             |       v
                             |  新进程启动
```

## 11. 关键日志分析

### 11.1 常见日志

```bash
# 进程死亡日志
ActivityManager: Process <package> (pid <pid>) has died: <adj> <procState>

# BinderDied 触发
ActivityManager: Death received in AppDeathRecipient for thread android.app.IApplicationThread$Stub$Proxy

# Service 清理
ActivityManager: Killing <package> (adj <adj>): kill background
ActivityManager: Force stopping <package> appid=<uid>

# Activity 清理  
ActivityTaskManager: Force removing ActivityRecord{...}: app died, no saved state

# 进程重启
ActivityManager: Start proc <pid>:<package>/u0a<uid> for <reason>
```

### 11.2 调试命令

```bash
# 查看进程状态
adb shell dumpsys activity processes

# 查看 Service 状态
adb shell dumpsys activity services

# 查看 Provider 状态
adb shell dumpsys activity providers

# 实时监控进程死亡
adb logcat -s ActivityManager:I | grep -E "(has died|Death received|Force removing)"
```

## 12. 总结

当应用进程挂掉后，AMS 通过 BinderDied 机制执行以下操作：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | `binderDied()` 触发 | Binder 驱动通知 AMS |
| 2 | `appDiedLocked()` | 进入核心处理入口 |
| 3 | 清理 Service | 通知客户端 unbind，决定是否重启 |
| 4 | 清理 Provider | 断开连接，通知客户端 |
| 5 | 清理 Receiver | 移除动态注册的广播 |
| 6 | 清理 Activity | 销毁 Activity，恢复栈顶 |
| 7 | 清理其他资源 | Alarm、Wakelock、Notification 等 |
| 8 | 通知 WMS | 清理进程相关窗口 |
| 9 | 判断重启 | Persistent 应用或有待处理任务则重启 |

整个过程保证了系统资源的正确释放，并对需要的组件进行自动恢复。
