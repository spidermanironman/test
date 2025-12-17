# Android linkToDeath 机制详解

## 1. 概述

`linkToDeath` 是 Android Binder IPC 机制中的一个重要特性，它允许一个进程**监听另一个进程的死亡事件**。当远程进程意外终止时，本地进程可以收到通知并进行相应的处理（如资源清理、重新连接等）。

## 2. 基本原理

### 2.1 Binder 通信模型回顾

```
┌─────────────────┐                    ┌─────────────────┐
│   Client 进程    │                    │   Server 进程    │
│                 │                    │                 │
│  ┌───────────┐  │    Binder Driver   │  ┌───────────┐  │
│  │ BpBinder  │◄─┼────────────────────┼─►│ BBinder   │  │
│  │ (Proxy)   │  │                    │  │ (Stub)    │  │
│  └───────────┘  │                    │  └───────────┘  │
└─────────────────┘                    └─────────────────┘
```

在 Binder 通信中：
- **Client** 持有远程服务的代理对象（BpBinder/BinderProxy）
- **Server** 持有实际的服务实现（BBinder/Binder）
- **Binder Driver** 负责跨进程通信和生命周期管理

### 2.2 linkToDeath 工作流程

```
┌──────────────────────────────────────────────────────────────────────┐
│                        linkToDeath 工作流程                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. 注册阶段                                                          │
│  ┌─────────┐    linkToDeath()     ┌───────────────┐                 │
│  │ Client  │ ──────────────────►  │ Binder Driver │                 │
│  └─────────┘                      │  (注册死亡通知) │                 │
│                                   └───────────────┘                 │
│                                                                      │
│  2. 监听阶段                                                          │
│  ┌───────────────┐     监控      ┌─────────┐                        │
│  │ Binder Driver │ ─────────────►│ Server  │                        │
│  └───────────────┘               └─────────┘                        │
│                                                                      │
│  3. 通知阶段 (Server 死亡时)                                          │
│  ┌─────────┐    binderDied()     ┌───────────────┐                 │
│  │ Client  │ ◄────────────────── │ Binder Driver │                 │
│  └─────────┘                      └───────────────┘                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

## 3. 核心 API

### 3.1 DeathRecipient 接口

```java
// Java 层
public interface IBinder {
    /**
     * 死亡通知接收者接口
     */
    public interface DeathRecipient {
        /**
         * 当远程进程死亡时被调用
         * 注意：此回调在 Binder 线程中执行
         */
        public void binderDied();
    }
    
    /**
     * 注册死亡通知
     * @param recipient 死亡通知接收者
     * @param flags 标志位，通常为 0
     */
    public void linkToDeath(DeathRecipient recipient, int flags)
            throws RemoteException;
    
    /**
     * 取消注册死亡通知
     * @param recipient 之前注册的接收者
     * @param flags 标志位，通常为 0
     * @return 是否成功取消
     */
    public boolean unlinkToDeath(DeathRecipient recipient, int flags);
}
```

### 3.2 Native 层接口

```cpp
// C++ 层 (frameworks/native/libs/binder/include/binder/IBinder.h)
class IBinder : public virtual RefBase {
public:
    class DeathRecipient : public virtual RefBase {
    public:
        virtual void binderDied(const wp<IBinder>& who) = 0;
    };
    
    virtual status_t linkToDeath(const sp<DeathRecipient>& recipient,
                                  void* cookie = nullptr,
                                  uint32_t flags = 0) = 0;
                                  
    virtual status_t unlinkToDeath(const wp<DeathRecipient>& recipient,
                                    void* cookie = nullptr,
                                    uint32_t flags = 0,
                                    wp<DeathRecipient>* outRecipient = nullptr) = 0;
};
```

## 4. 实现原理深入分析

### 4.1 内核层实现

Binder 驱动在内核中维护了一个死亡通知链表：

```c
// drivers/android/binder.c

// 死亡通知结构体
struct binder_ref_death {
    struct binder_work work;          // 工作队列节点
    binder_uintptr_t cookie;          // 用户空间回调标识
};

// binder 引用结构体
struct binder_ref {
    struct binder_ref_data data;
    struct rb_node rb_node_desc;
    struct rb_node rb_node_node;
    struct hlist_node node_entry;
    struct binder_proc *proc;
    struct binder_node *node;
    struct binder_ref_death *death;   // 死亡通知指针
};
```

### 4.2 注册流程 (linkToDeath)

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         linkToDeath 注册流程                               │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Java/Native 层                    Kernel 层                              │
│  ┌──────────────────┐             ┌─────────────────────────────────┐    │
│  │ 1. linkToDeath() │             │                                 │    │
│  │    调用          │             │                                 │    │
│  └────────┬─────────┘             │                                 │    │
│           │                        │                                 │    │
│           ▼                        │                                 │    │
│  ┌──────────────────┐             │                                 │    │
│  │ 2. 创建          │             │                                 │    │
│  │ DeathRecipient   │             │                                 │    │
│  │ JavaDeathRecipient│            │                                 │    │
│  └────────┬─────────┘             │                                 │    │
│           │                        │                                 │    │
│           ▼                        │                                 │    │
│  ┌──────────────────┐             │                                 │    │
│  │ 3. ioctl         │────────────►│ 4. binder_ioctl()              │    │
│  │ BC_REQUEST_      │             │    ├─ BC_REQUEST_DEATH_         │    │
│  │ DEATH_NOTIFICATION│            │    │  NOTIFICATION              │    │
│  └──────────────────┘             │    └─ 创建 binder_ref_death     │    │
│                                   │       挂载到 binder_ref->death   │    │
│                                   └─────────────────────────────────┘    │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

关键代码路径：

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
            if (mObituaries == nullptr) {
                mObituaries = new Vector<Obituary>;
                if (mObituaries == nullptr) {
                    return NO_MEMORY;
                }
                // 向 Binder 驱动注册死亡通知
                IPCThreadState::self()->requestDeathNotification(
                    mHandle, this);
            }
            mObituaries->push(ob);
            return NO_ERROR;
        }
    }
    return DEAD_OBJECT;
}
```

### 4.3 死亡通知流程

当 Server 进程死亡时：

```
┌───────────────────────────────────────────────────────────────────────────┐
│                        Server 进程死亡通知流程                              │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  1. Server 进程退出                                                        │
│     │                                                                     │
│     ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ 2. Kernel: binder_release() / binder_deferred_release()         │     │
│  │    - 遍历该进程的所有 binder_node                                 │     │
│  │    - 找到所有引用该 node 的 binder_ref                            │     │
│  │    - 检查 ref->death 是否非空                                     │     │
│  └────────────────────────────┬────────────────────────────────────┘     │
│                               │                                           │
│                               ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ 3. Kernel: binder_send_death_notification()                      │     │
│  │    - 将 death->work 添加到 client proc 的 todo 队列               │     │
│  │    - 唤醒等待的 client 线程                                       │     │
│  └────────────────────────────┬────────────────────────────────────┘     │
│                               │                                           │
│                               ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ 4. Client 的 Binder 线程被唤醒                                    │     │
│  │    - binder_thread_read() 读取 BR_DEAD_BINDER                     │     │
│  │    - 返回用户空间                                                  │     │
│  └────────────────────────────┬────────────────────────────────────┘     │
│                               │                                           │
│                               ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ 5. Native/Java: 处理 BR_DEAD_BINDER                              │     │
│  │    - IPCThreadState::executeCommand()                            │     │
│  │    - BpBinder::sendObituary()                                    │     │
│  │    - 回调 DeathRecipient::binderDied()                           │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

### 4.4 内核关键代码

```c
// drivers/android/binder.c

static void binder_release_work(struct binder_proc *proc,
                                struct list_head *list) {
    struct binder_work *w;
    
    while (!list_empty(list)) {
        w = list_first_entry(list, struct binder_work, entry);
        
        switch (w->type) {
        case BINDER_WORK_DEAD_BINDER:
        case BINDER_WORK_DEAD_BINDER_AND_CLEAR:
        case BINDER_WORK_CLEAR_DEATH_NOTIFICATION: {
            struct binder_ref_death *death;
            death = container_of(w, struct binder_ref_death, work);
            // 处理死亡通知...
        } break;
        // ...
        }
    }
}

// 发送死亡通知
static void binder_send_death_notification(struct binder_proc *proc,
                                           struct binder_ref *ref) {
    if (ref->death) {
        // 将死亡通知工作项添加到客户端进程的待办队列
        ref->death->work.type = BINDER_WORK_DEAD_BINDER;
        list_add_tail(&ref->death->work.entry, &proc->todo);
        wake_up_interruptible(&proc->wait);
    }
}
```

## 5. 使用示例

### 5.1 Java 层使用

```java
public class ServiceConnection {
    private IRemoteService mService;
    private IBinder mBinder;
    
    // 定义死亡通知接收者
    private IBinder.DeathRecipient mDeathRecipient = new IBinder.DeathRecipient() {
        @Override
        public void binderDied() {
            Log.w(TAG, "Remote service died!");
            
            // 清理资源
            if (mBinder != null) {
                mBinder.unlinkToDeath(this, 0);
                mBinder = null;
            }
            mService = null;
            
            // 尝试重新连接
            reconnectService();
        }
    };
    
    public void onServiceConnected(ComponentName name, IBinder binder) {
        mBinder = binder;
        mService = IRemoteService.Stub.asInterface(binder);
        
        try {
            // 注册死亡通知
            binder.linkToDeath(mDeathRecipient, 0);
            Log.d(TAG, "linkToDeath registered successfully");
        } catch (RemoteException e) {
            Log.e(TAG, "Failed to link to death", e);
        }
    }
    
    public void onServiceDisconnected() {
        // 取消注册
        if (mBinder != null) {
            mBinder.unlinkToDeath(mDeathRecipient, 0);
        }
    }
}
```

### 5.2 Native 层使用

```cpp
class MyDeathRecipient : public IBinder::DeathRecipient {
public:
    MyDeathRecipient(const std::string& serviceName) 
        : mServiceName(serviceName) {}
    
    virtual void binderDied(const wp<IBinder>& who) override {
        ALOGW("Service %s died!", mServiceName.c_str());
        
        // 处理服务死亡
        // 1. 清理本地缓存的引用
        // 2. 通知上层
        // 3. 尝试重新获取服务
        
        sp<IBinder> binder = who.promote();
        if (binder != nullptr) {
            binder->unlinkToDeath(this);
        }
    }
    
private:
    std::string mServiceName;
};

// 使用示例
void connectToService() {
    sp<IServiceManager> sm = defaultServiceManager();
    sp<IBinder> binder = sm->getService(String16("my.service"));
    
    if (binder != nullptr) {
        sp<MyDeathRecipient> deathRecipient = 
            new MyDeathRecipient("my.service");
        
        status_t status = binder->linkToDeath(deathRecipient);
        if (status != NO_ERROR) {
            ALOGE("Failed to link to death: %d", status);
        }
    }
}
```

## 6. 典型应用场景

### 6.1 ActivityManagerService 监控应用进程

```java
// frameworks/base/services/core/java/com/android/server/am/ProcessRecord.java

// AMS 通过 linkToDeath 监控应用进程
class AppDeathRecipient implements IBinder.DeathRecipient {
    final ProcessRecord mApp;
    final int mPid;
    final ApplicationThread mAppThread;

    @Override
    public void binderDied() {
        // 应用进程死亡，清理相关资源
        synchronized(ActivityManagerService.this) {
            appDiedLocked(mApp, mPid, mAppThread, true);
        }
    }
}
```

### 6.2 WindowManagerService 监控窗口客户端

```java
// 当应用创建窗口时，WMS 会监控其死亡
class WindowState {
    final DeathRecipient mDeathRecipient;
    
    WindowState(...) {
        mDeathRecipient = new DeathRecipient();
        try {
            // 监控窗口所属进程
            mClient.asBinder().linkToDeath(mDeathRecipient, 0);
        } catch (RemoteException e) {
            // Client already dead
        }
    }
    
    private class DeathRecipient implements IBinder.DeathRecipient {
        @Override
        public void binderDied() {
            // 客户端死亡，移除窗口
            mService.windowCloseOnRemoval(WindowState.this);
        }
    }
}
```

### 6.3 ServiceManager 管理服务注册

```cpp
// frameworks/native/cmds/servicemanager/ServiceManager.cpp

// 服务注册时监控服务进程
Status ServiceManager::addService(const std::string& name,
                                   const sp<IBinder>& binder,
                                   bool allowIsolated,
                                   int32_t dumpPriority) {
    // ...
    
    // 监控服务进程死亡
    auto death = [name]() {
        ALOGI("Service %s has died", name.c_str());
    };
    
    auto linkRet = binder->linkToDeath(death);
    
    // ...
}
```

## 7. 注意事项和最佳实践

### 7.1 线程安全

```java
/**
 * 重要：binderDied() 回调在 Binder 线程池中执行
 * 不是在主线程！
 */
public void binderDied() {
    // ❌ 错误：直接更新 UI
    textView.setText("Service died");
    
    // ✅ 正确：切换到主线程
    mainHandler.post(() -> {
        textView.setText("Service died");
    });
}
```

### 7.2 避免内存泄漏

```java
// ❌ 错误：匿名内部类持有外部类引用
class MyActivity extends Activity {
    private IBinder mBinder;
    
    void onServiceConnected(IBinder binder) {
        mBinder = binder;
        // 匿名内部类隐式持有 MyActivity.this
        binder.linkToDeath(new DeathRecipient() {
            @Override
            public void binderDied() {
                // 即使 Activity 已销毁，仍然持有引用
            }
        }, 0);
    }
}

// ✅ 正确：使用静态内部类 + 弱引用
class MyActivity extends Activity {
    private DeathRecipient mDeathRecipient;
    
    private static class DeathRecipient implements IBinder.DeathRecipient {
        private WeakReference<MyActivity> mActivityRef;
        
        DeathRecipient(MyActivity activity) {
            mActivityRef = new WeakReference<>(activity);
        }
        
        @Override
        public void binderDied() {
            MyActivity activity = mActivityRef.get();
            if (activity != null) {
                activity.handleServiceDeath();
            }
        }
    }
}
```

### 7.3 正确的生命周期管理

```java
class ServiceConnectionManager {
    private IBinder mBinder;
    private DeathRecipient mDeathRecipient;
    
    public void connect(IBinder binder) {
        // 清理旧连接
        disconnect();
        
        mBinder = binder;
        mDeathRecipient = new MyDeathRecipient();
        
        try {
            binder.linkToDeath(mDeathRecipient, 0);
        } catch (RemoteException e) {
            // 服务已经死亡
            handleServiceDeath();
        }
    }
    
    public void disconnect() {
        if (mBinder != null && mDeathRecipient != null) {
            // 重要：取消注册，避免泄漏
            mBinder.unlinkToDeath(mDeathRecipient, 0);
        }
        mBinder = null;
        mDeathRecipient = null;
    }
}
```

## 8. 与其他机制的对比

| 特性 | linkToDeath | ServiceConnection.onServiceDisconnected |
|------|-------------|----------------------------------------|
| 触发条件 | 进程死亡 | Service unbind 或进程死亡 |
| 通知时机 | 几乎立即 | 可能有延迟 |
| 适用范围 | 任何 IBinder | 仅 bindService 场景 |
| 实现层级 | Binder 驱动层 | Framework 层 |
| 可靠性 | 非常可靠 | 依赖 AMS 状态 |

## 9. 调试技巧

### 9.1 查看 Binder 死亡通知状态

```bash
# 查看进程的 Binder 信息
adb shell cat /sys/kernel/debug/binder/proc/<pid>

# 查看所有 Binder 状态
adb shell cat /sys/kernel/debug/binder/state
```

### 9.2 日志过滤

```bash
# 查看死亡通知相关日志
adb logcat | grep -E "binderDied|DeathRecipient|DEAD_BINDER"
```

## 10. 总结

`linkToDeath` 机制是 Android Binder IPC 中的重要特性：

1. **核心功能**：监听远程进程死亡，实现跨进程生命周期感知
2. **实现层级**：内核 Binder 驱动 → Native 层 → Java 层
3. **工作流程**：注册 → 监听 → 通知
4. **典型应用**：AMS 监控应用、WMS 监控窗口、ServiceManager 管理服务
5. **注意事项**：线程安全、避免泄漏、正确的生命周期管理

这个机制使得 Android 系统能够及时感知和处理进程死亡事件，是保证系统稳定性的关键组件之一。
