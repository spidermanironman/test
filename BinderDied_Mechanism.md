# BinderDied 机制详解

## 1. 概述

BinderDied 是 Android Binder IPC（进程间通信）机制中的**死亡通知**机制。当一个 Binder 服务端进程意外终止（crash、被 kill、ANR 等）时，系统会通知所有持有该服务 Binder 引用的客户端进程，使其能够进行相应的清理和恢复操作。

## 2. 核心组件

### 2.1 DeathRecipient 接口

```java
// Android Framework 层定义
public interface IBinder {
    /**
     * 死亡通知回调接口
     */
    public interface DeathRecipient {
        public void binderDied();
    }
    
    // 注册死亡通知
    public void linkToDeath(DeathRecipient recipient, int flags) throws RemoteException;
    
    // 取消注册
    public boolean unlinkToDeath(DeathRecipient recipient, int flags);
}
```

### 2.2 Native 层对应接口

```cpp
// frameworks/native/include/binder/IBinder.h
class DeathRecipient : public virtual RefBase {
public:
    virtual void binderDied(const wp<IBinder>& who) = 0;
};

status_t linkToDeath(const sp<DeathRecipient>& recipient,
                     void* cookie = nullptr, uint32_t flags = 0);
status_t unlinkToDeath(const wp<DeathRecipient>& recipient,
                       void* cookie = nullptr, uint32_t flags = 0,
                       wp<DeathRecipient>* outRecipient = nullptr);
```

## 3. 工作原理

### 3.1 注册流程

```
客户端进程                    Binder 驱动                    服务端进程
    |                            |                              |
    |  1. linkToDeath()          |                              |
    |--------------------------->|                              |
    |                            |  2. 记录 death 注册信息      |
    |                            |     (binder_ref_death)       |
    |                            |                              |
    |  3. 返回成功               |                              |
    |<---------------------------|                              |
```

### 3.2 死亡通知流程

```
客户端进程                    Binder 驱动                    服务端进程
    |                            |                              |
    |                            |  1. 服务端进程死亡           |
    |                            |<-----------------------------X
    |                            |                              
    |                            |  2. 遍历所有 death 注册      
    |                            |     发送 BR_DEAD_BINDER      
    |  3. BR_DEAD_BINDER         |                              
    |<---------------------------|                              
    |                            |                              
    |  4. 调用 binderDied()      |                              
    |                            |                              
    |  5. BC_DEAD_BINDER_DONE    |                              
    |--------------------------->|                              
```

## 4. 内核驱动层实现

### 4.1 关键数据结构

```c
// drivers/android/binder.c

// 死亡通知注册信息
struct binder_ref_death {
    struct binder_work work;        // 工作队列项
    binder_uintptr_t cookie;        // 用户态回调标识
};

// Binder 引用结构
struct binder_ref {
    struct binder_ref_data data;
    struct rb_node rb_node_desc;    // 按 handle 排序的红黑树节点
    struct rb_node rb_node_node;    // 按 node 排序的红黑树节点
    struct hlist_node node_entry;   // node 的引用列表
    struct binder_proc *proc;       // 所属进程
    struct binder_node *node;       // 指向的目标节点
    struct binder_ref_death *death; // 死亡通知信息
};
```

### 4.2 linkToDeath 内核处理

```c
static int binder_thread_write(struct binder_proc *proc,
                               struct binder_thread *thread,
                               binder_uintptr_t binder_buffer,
                               size_t size,
                               binder_size_t *consumed) {
    // ...
    case BC_REQUEST_DEATH_NOTIFICATION: {
        uint32_t target;
        binder_uintptr_t cookie;
        struct binder_ref *ref;
        struct binder_ref_death *death = NULL;

        // 获取 handle 和 cookie
        if (get_user(target, (uint32_t __user *)ptr))
            return -EFAULT;
        ptr += sizeof(uint32_t);
        if (get_user(cookie, (binder_uintptr_t __user *)ptr))
            return -EFAULT;
        ptr += sizeof(binder_uintptr_t);

        // 查找对应的 binder_ref
        ref = binder_get_ref_olocked(proc, target, false);
        
        // 分配 death 结构
        death = kzalloc(sizeof(*death), GFP_KERNEL);
        INIT_LIST_HEAD(&death->work.entry);
        death->cookie = cookie;
        ref->death = death;
        
        // 如果目标节点的进程已经死亡，立即加入工作队列
        if (ref->node->proc == NULL) {
            ref->death->work.type = BINDER_WORK_DEAD_BINDER;
            binder_enqueue_work_ilocked(&ref->death->work,
                                        &thread->todo);
        }
    }
    // ...
}
```

### 4.3 进程死亡时的处理

```c
static void binder_deferred_release(struct binder_proc *proc) {
    struct binder_node *node;
    struct binder_ref *ref;
    
    // 遍历该进程的所有 binder_node
    while ((node = rb_entry(rb_first(&proc->nodes), 
                           struct binder_node, rb_node))) {
        // 获取所有引用该 node 的 ref
        hlist_for_each_entry(ref, &node->refs, node_entry) {
            // 如果注册了死亡通知
            if (ref->death) {
                // 设置工作类型为 DEAD_BINDER
                ref->death->work.type = BINDER_WORK_DEAD_BINDER;
                
                // 将死亡通知加入客户端进程的工作队列
                binder_enqueue_work(ref->proc, 
                                   &ref->death->work);
                                   
                // 唤醒客户端进程
                binder_wakeup_proc_ilocked(ref->proc);
            }
        }
        // 删除 node
        rb_erase(&node->rb_node, &proc->nodes);
        binder_free_node(node);
    }
}
```

## 5. Framework 层实现

### 5.1 Java 层 linkToDeath

```java
// frameworks/base/core/java/android/os/BinderProxy.java
public native void linkToDeath(DeathRecipient recipient, int flags)
        throws RemoteException;
```

### 5.2 JNI 层实现

```cpp
// frameworks/base/core/jni/android_util_Binder.cpp

// Java DeathRecipient 的包装类
class JavaDeathRecipient : public IBinder::DeathRecipient {
public:
    JavaDeathRecipient(JNIEnv* env, jobject object, 
                       const sp<DeathRecipientList>& list)
        : mVM(jnienv_to_javavm(env)),
          mObject(env->NewGlobalRef(object)),
          mObjectWeak(NULL),
          mList(list) {
        list->add(this);
    }

    // 死亡通知回调
    void binderDied(const wp<IBinder>& who) {
        if (mObject != NULL) {
            JNIEnv* env = javavm_to_jnienv(mVM);
            // 调用 Java 层的 binderDied() 方法
            env->CallVoidMethod(mObject, 
                gBinderProxyOffsets.mGetInstance);
            env->CallVoidMethod(mObject, 
                gDeathRecipientOffsets.mMethod_binderDied);
            // ...
        }
    }
};

static void android_os_BinderProxy_linkToDeath(JNIEnv* env, 
                                               jobject obj,
                                               jobject recipient, 
                                               jint flags) {
    if (recipient == NULL) {
        jniThrowNullPointerException(env, NULL);
        return;
    }

    BinderProxyNativeData* nd = getBPNativeData(env, obj);
    IBinder* target = nd->mObject.get();

    // 创建 JavaDeathRecipient
    sp<JavaDeathRecipient> jdr = new JavaDeathRecipient(env, recipient, 
                                                        nd->mOrgue);
    
    // 调用 Native Binder 的 linkToDeath
    status_t err = target->linkToDeath(jdr, NULL, flags);
    
    if (err != NO_ERROR) {
        jdr->clearReference();
        signalExceptionForError(env, obj, err, true);
    }
}
```

### 5.3 BpBinder 层实现

```cpp
// frameworks/native/libs/binder/BpBinder.cpp

status_t BpBinder::linkToDeath(const sp<DeathRecipient>& recipient,
                               void* cookie, uint32_t flags) {
    Obituary ob;
    ob.recipient = recipient;
    ob.cookie = cookie;
    ob.flags = flags;

    {
        AutoMutex _l(mLock);
        
        if (!mObitsSent) {
            if (!mObituaries) {
                mObituaries = new Vector<Obituary>;
                if (!mObituaries) {
                    return NO_MEMORY;
                }
                // 首次注册，发送命令到驱动
                IPCThreadState::self()->requestDeathNotification(
                    mHandle, this);
                IPCThreadState::self()->flushCommands();
            }
            // 添加到本地列表
            mObituaries->push(ob);
            return NO_ERROR;
        }
    }
    
    // 如果已经死亡，立即通知
    return DEAD_OBJECT;
}

void BpBinder::sendObituary() {
    mLock.lock();
    Vector<Obituary>* obits = mObituaries;
    if (obits != nullptr) {
        mObituaries = nullptr;
        mObitsSent = 1;
        mLock.unlock();

        // 遍历所有注册的 DeathRecipient，调用 binderDied
        const size_t N = obits->size();
        for (size_t i = 0; i < N; i++) {
            // 调用回调
            obits->itemAt(i).recipient->binderDied(wp<IBinder>(this));
        }

        delete obits;
    }
}
```

## 6. 典型使用场景

### 6.1 ActivityManagerService 监控应用进程

```java
// AMS 监控应用进程死亡
private class AppDeathRecipient implements IBinder.DeathRecipient {
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
        synchronized(ActivityManagerService.this) {
            // 进程死亡处理
            appDiedLocked(mApp, mPid, mAppThread, true, null);
        }
    }
}

// 注册监控
public void attachApplicationLocked(IApplicationThread thread, 
                                    int pid, int callingUid,
                                    long startSeq) {
    ProcessRecord app;
    // ...
    try {
        AppDeathRecipient adr = new AppDeathRecipient(app, pid, thread);
        thread.asBinder().linkToDeath(adr, 0);
        app.deathRecipient = adr;
    } catch (RemoteException e) {
        // 注册失败，进程可能已死
        app.resetPackageList(mProcessStats);
        return false;
    }
}
```

### 6.2 ServiceConnection 监控远程服务

```java
// 客户端监控远程服务死亡
private IBinder.DeathRecipient mDeathRecipient = new IBinder.DeathRecipient() {
    @Override
    public void binderDied() {
        // 服务端进程死亡
        Log.w(TAG, "Remote service died");
        
        // 清理资源
        mRemoteService = null;
        
        // 尝试重连
        if (mShouldReconnect) {
            mHandler.postDelayed(() -> bindToService(), RECONNECT_DELAY);
        }
    }
};

// 绑定服务时注册
private ServiceConnection mConnection = new ServiceConnection() {
    @Override
    public void onServiceConnected(ComponentName name, IBinder service) {
        try {
            service.linkToDeath(mDeathRecipient, 0);
            mRemoteService = IMyService.Stub.asInterface(service);
        } catch (RemoteException e) {
            Log.e(TAG, "Service already dead");
        }
    }
    
    @Override
    public void onServiceDisconnected(ComponentName name) {
        // 注意：这与 binderDied 不同，这是解绑导致的
    }
};
```

### 6.3 WindowManagerService 监控窗口 Token

```java
// WMS 监控 Activity 的窗口 Token
class WindowToken implements IBinder.DeathRecipient {
    final IBinder token;
    
    WindowToken(IBinder token, int type, boolean persistOnEmpty) {
        this.token = token;
        // ...
        try {
            token.linkToDeath(this, 0);
        } catch (RemoteException e) {
            // Token 已死
        }
    }
    
    @Override
    public void binderDied() {
        synchronized (mService.mGlobalLock) {
            // Token 对应的进程死亡，清理相关窗口
            removeAllWindowsIfPossible();
        }
    }
}
```

## 7. binderDied vs onServiceDisconnected

| 特性 | binderDied | onServiceDisconnected |
|------|------------|----------------------|
| 触发时机 | 服务端进程死亡 | 服务连接断开（多种原因） |
| 调用位置 | Binder 线程 | 主线程 |
| 触发原因 | 仅进程死亡 | 进程死亡、unbind、服务停止等 |
| 需要手动注册 | 是（linkToDeath） | 否（ServiceConnection 回调） |
| 可用于非 Service | 是（任何 Binder） | 否（仅 bound Service） |

## 8. 常见问题与最佳实践

### 8.1 正确使用模式

```java
class ServiceClient {
    private IRemoteService mService;
    private IBinder mServiceBinder;
    private volatile boolean mBound = false;
    
    private final IBinder.DeathRecipient mDeathRecipient = 
        new IBinder.DeathRecipient() {
            @Override
            public void binderDied() {
                // 在 Binder 线程执行，注意线程安全
                synchronized (ServiceClient.this) {
                    if (mServiceBinder != null) {
                        mServiceBinder.unlinkToDeath(this, 0);
                        mServiceBinder = null;
                    }
                    mService = null;
                    mBound = false;
                }
                // 通知 UI 线程
                mHandler.post(() -> onServiceDied());
            }
        };
    
    public void connect(IBinder binder) {
        synchronized (this) {
            mServiceBinder = binder;
            try {
                binder.linkToDeath(mDeathRecipient, 0);
                mService = IRemoteService.Stub.asInterface(binder);
                mBound = true;
            } catch (RemoteException e) {
                // 服务已死
                mServiceBinder = null;
                mService = null;
            }
        }
    }
    
    public void disconnect() {
        synchronized (this) {
            if (mServiceBinder != null) {
                // 重要：必须调用 unlinkToDeath 避免内存泄漏
                mServiceBinder.unlinkToDeath(mDeathRecipient, 0);
                mServiceBinder = null;
            }
            mService = null;
            mBound = false;
        }
    }
}
```

### 8.2 避免内存泄漏

```java
// 错误示例：匿名内部类持有外部类引用
class BadExample extends Activity {
    private IBinder mBinder;
    
    void onBind(IBinder binder) {
        mBinder = binder;
        // 错误：Activity 销毁后，DeathRecipient 仍持有 Activity 引用
        binder.linkToDeath(new IBinder.DeathRecipient() {
            @Override
            public void binderDied() {
                // 隐式持有 BadExample.this
                updateUI();
            }
        }, 0);
    }
}

// 正确示例：使用静态内部类 + 弱引用
class GoodExample extends Activity {
    private IBinder mBinder;
    private MyDeathRecipient mRecipient;
    
    private static class MyDeathRecipient implements IBinder.DeathRecipient {
        private final WeakReference<GoodExample> mActivityRef;
        
        MyDeathRecipient(GoodExample activity) {
            mActivityRef = new WeakReference<>(activity);
        }
        
        @Override
        public void binderDied() {
            GoodExample activity = mActivityRef.get();
            if (activity != null && !activity.isFinishing()) {
                activity.mHandler.post(() -> activity.onServiceDied());
            }
        }
    }
    
    void onBind(IBinder binder) {
        mBinder = binder;
        mRecipient = new MyDeathRecipient(this);
        try {
            binder.linkToDeath(mRecipient, 0);
        } catch (RemoteException e) {
            // 处理错误
        }
    }
    
    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (mBinder != null && mRecipient != null) {
            mBinder.unlinkToDeath(mRecipient, 0);
        }
    }
}
```

### 8.3 线程安全注意事项

```java
/**
 * binderDied() 在 Binder 线程池中执行，不在主线程
 * 需要注意：
 * 1. 不能直接操作 UI
 * 2. 需要同步访问共享资源
 * 3. 考虑使用 Handler 切换到主线程
 */
private final IBinder.DeathRecipient mDeathRecipient = () -> {
    // 切换到主线程处理 UI 更新
    mHandler.post(() -> {
        Toast.makeText(mContext, "Service died", Toast.LENGTH_SHORT).show();
        updateConnectionStatus(false);
    });
};
```

## 9. 调试与排查

### 9.1 查看 Binder 死亡通知日志

```bash
# 查看 Binder 相关日志
adb logcat -s Binder:V

# 查看进程死亡相关日志
adb logcat | grep -E "(binderDied|DEAD_BINDER|died|crash)"

# 查看 AMS 进程管理日志
adb logcat -s ActivityManager:V
```

### 9.2 Binder 驱动调试

```bash
# 查看 Binder 统计信息
adb shell cat /sys/kernel/debug/binder/stats

# 查看特定进程的 Binder 信息
adb shell cat /sys/kernel/debug/binder/proc/<pid>

# 查看 Binder 事务
adb shell cat /sys/kernel/debug/binder/transactions
```

## 10. 总结

BinderDied 机制是 Android Binder IPC 的重要组成部分，提供了可靠的进程死亡检测能力：

1. **内核驱动支持**：Binder 驱动维护死亡通知的注册信息，在目标进程死亡时主动通知客户端
2. **异步通知**：通过 BR_DEAD_BINDER 命令异步通知，不阻塞客户端
3. **资源清理**：帮助客户端及时释放与死亡进程相关的资源
4. **高可靠性**：由内核保证，即使服务端异常崩溃也能正确通知

正确使用 BinderDied 机制可以：
- 提高应用的健壮性
- 及时发现并处理服务异常
- 实现自动重连等容错逻辑
- 避免资源泄漏
