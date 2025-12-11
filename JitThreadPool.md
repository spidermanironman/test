# JitThreadPool 详解

## 一、概述

`JitThreadPool` 是 Android ART (Android Runtime) 虚拟机中用于管理 **JIT (Just-In-Time) 编译任务** 的线程池。

### 1.1 什么是 JIT 编译？

```
┌─────────────────────────────────────────────────────────────────┐
│                     ART 编译模式                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │    AOT      │    │ 解释执行     │    │    JIT      │          │
│  │ (安装时编译) │    │ (逐行解释)   │    │ (运行时编译) │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│        │                  │                  │                   │
│        ▼                  ▼                  ▼                   │
│   安装时将 DEX        运行时逐条          运行时将热点代码         │
│   编译为机器码        解释字节码          编译为机器码             │
│   (慢安装，快执行)    (快启动，慢执行)    (平衡启动和执行)         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 JitThreadPool 的作用

- 管理一组工作线程，专门执行 JIT 编译任务
- 异步编译热点方法，不阻塞主线程
- 提高应用运行时性能

---

## 二、JitThreadPool 架构

### 2.1 类继承关系

```
┌─────────────────────┐
│     ThreadPool      │  ← 基类：通用线程池
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   JitThreadPool     │  ← JIT 专用线程池
└─────────────────────┘
```

### 2.2 核心组件

```
┌─────────────────────────────────────────────────────────────────────┐
│                        JitThreadPool                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐             │
│  │   Worker 1   │   │   Worker 2   │   │   Worker N   │             │
│  │  (编译线程)   │   │  (编译线程)   │   │  (编译线程)   │             │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘             │
│         │                  │                  │                      │
│         └──────────────────┼──────────────────┘                      │
│                            │                                         │
│                            ▼                                         │
│                   ┌─────────────────┐                                │
│                   │   Task Queue    │  ← 编译任务队列                 │
│                   │  (待编译方法)    │                                │
│                   └─────────────────┘                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、源码分析

### 3.1 ThreadPool 基类

**位置**：`art/runtime/thread_pool.h`

```cpp
// art/runtime/thread_pool.h

class ThreadPool {
 public:
  // 创建线程池
  ThreadPool(const char* name,
             size_t num_threads,
             bool create_peers = false,
             size_t worker_stack_size = kDefaultStackSize);
  
  virtual ~ThreadPool();
  
  // 启动所有工作线程
  void StartWorkers(Thread* self);
  
  // 停止所有工作线程
  void StopWorkers(Thread* self);
  
  // 添加任务到队列
  void AddTask(Thread* self, Task* task);
  
  // 等待所有任务完成
  void Wait(Thread* self, bool do_work, bool may_hold_locks);
  
 protected:
  const std::string name_;                    // 线程池名称
  std::vector<ThreadPoolWorker*> workers_;    // 工作线程列表
  TaskQueue task_queue_;                      // 任务队列
  
  Mutex task_queue_lock_;                     // 任务队列锁
  ConditionVariable task_queue_condition_;    // 条件变量
  
  volatile bool started_;                     // 是否已启动
  volatile bool shutting_down_;               // 是否正在关闭
};
```

### 3.2 JitThreadPool 类

**位置**：`art/runtime/jit/jit_thread_pool.h`

```cpp
// art/runtime/jit/jit_thread_pool.h

class JitThreadPool : public ThreadPool {
 public:
  // 创建 JIT 线程池
  static JitThreadPool* Create(const char* name,
                                size_t num_threads,
                                size_t worker_stack_size = kDefaultStackSize);
  
  // 添加 JIT 编译任务
  void AddTask(Thread* self, JitCompileTask* task);
  
  // 获取线程池实例
  static JitThreadPool* GetSingleton();
  
 private:
  JitThreadPool(const char* name, size_t num_threads, size_t worker_stack_size);
  
  // JIT 特定的配置
  static constexpr size_t kJitPoolSize = 1;  // 默认1个编译线程
};
```

### 3.3 ThreadPoolWorker 工作线程

```cpp
// art/runtime/thread_pool.cc

class ThreadPoolWorker {
 public:
  ThreadPoolWorker(ThreadPool* thread_pool,
                   const std::string& name,
                   size_t stack_size);
  
  // 工作线程主循环
  void Run() {
    Thread* self = Thread::Current();
    
    while (true) {
      // 从队列获取任务
      Task* task = thread_pool_->TakeTask(self);
      
      if (task == nullptr) {
        // 线程池关闭，退出
        break;
      }
      
      // 执行任务（JIT 编译）
      task->Run(self);
      
      // 任务完成，释放
      task->Finalize();
    }
  }
  
 private:
  ThreadPool* thread_pool_;
  std::string name_;
  std::unique_ptr<std::thread> thread_;
};
```

---

## 四、JIT 编译任务

### 4.1 JitCompileTask

```cpp
// art/runtime/jit/jit.h

class JitCompileTask : public Task {
 public:
  enum class TaskKind {
    kCompile,           // 编译任务
    kPreCompile,        // 预编译任务
    kCompileBaseline,   // 基线编译
    kCompileOsr,        // OSR (On-Stack Replacement) 编译
  };
  
  JitCompileTask(ArtMethod* method,
                 TaskKind kind,
                 CompilationKind compilation_kind);
  
  // 执行编译
  void Run(Thread* self) override {
    // 调用 JIT 编译器编译方法
    bool success = jit_->CompileMethod(method_, self, compilation_kind_);
    
    if (success) {
      // 编译成功，更新方法入口点
      Runtime::Current()->GetInstrumentation()->UpdateMethodsCode(
          method_, 
          jit_->GetCodeCache()->GetCompiledCode(method_));
    }
  }
  
  void Finalize() override {
    delete this;
  }
  
 private:
  ArtMethod* method_;           // 要编译的方法
  TaskKind kind_;               // 任务类型
  CompilationKind compilation_kind_;
};
```

### 4.2 任务添加流程

```cpp
// art/runtime/jit/jit.cc

void Jit::AddCompileTask(Thread* self,
                         ArtMethod* method,
                         CompilationKind compilation_kind) {
  // 检查方法是否已编译
  if (code_cache_->ContainsMethod(method)) {
    return;  // 已编译，跳过
  }
  
  // 创建编译任务
  JitCompileTask* task = new JitCompileTask(
      method, 
      JitCompileTask::TaskKind::kCompile,
      compilation_kind);
  
  // 添加到线程池队列
  thread_pool_->AddTask(self, task);
}
```

---

## 五、JitThreadPool 工作流程

### 5.1 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        JIT 编译完整流程                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   App 执行代码                                                               │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────────────┐                                                        │
│   │  解释器执行方法   │                                                        │
│   │  并统计热度      │                                                        │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐     N                                                  │
│   │  热度 > 阈值？   │──────────────────┐                                     │
│   └────────┬────────┘                  │                                     │
│            │ Y                         │                                     │
│            ▼                           │                                     │
│   ┌─────────────────┐                  │                                     │
│   │  创建编译任务    │                  │                                     │
│   │  JitCompileTask │                  │                                     │
│   └────────┬────────┘                  │                                     │
│            │                           │                                     │
│            ▼                           │                                     │
│   ┌─────────────────┐                  │                                     │
│   │  添加到任务队列  │                  │                                     │
│   │  JitThreadPool  │                  │                                     │
│   └────────┬────────┘                  │                                     │
│            │                           │                                     │
│            ▼                           │                                     │
│   ┌─────────────────┐                  │                                     │
│   │  Worker 线程    │                  │                                     │
│   │  取出任务执行    │                  │                                     │
│   └────────┬────────┘                  │                                     │
│            │                           │                                     │
│            ▼                           │                                     │
│   ┌─────────────────┐                  │                                     │
│   │  JIT 编译器     │                  │                                     │
│   │  编译为机器码   │                  │                                     │
│   └────────┬────────┘                  │                                     │
│            │                           │                                     │
│            ▼                           │                                     │
│   ┌─────────────────┐                  │                                     │
│   │  存入 CodeCache │                  │                                     │
│   │  更新方法入口点  │                  │                                     │
│   └────────┬────────┘                  │                                     │
│            │                           │                                     │
│            ▼                           ▼                                     │
│   ┌─────────────────────────────────────────┐                                │
│   │         下次调用时直接执行机器码          │                                │
│   └─────────────────────────────────────────┘                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 热点检测

```cpp
// art/runtime/interpreter/interpreter.cc

// 解释执行时统计方法调用次数
void DoInterpret(Thread* self, ArtMethod* method, ...) {
  // 增加热度计数
  uint16_t hotness_count = method->IncrementCounter();
  
  // 检查是否达到 JIT 阈值
  if (hotness_count >= jit_threshold_) {
    // 触发 JIT 编译
    Runtime::Current()->GetJit()->AddCompileTask(self, method);
  }
  
  // 继续解释执行...
}
```

---

## 六、线程池管理

### 6.1 创建与初始化

```cpp
// art/runtime/jit/jit.cc

bool Jit::Create(JitOptions* options) {
  // 创建 JIT 线程池
  // 通常只有 1 个编译线程，避免过多资源消耗
  thread_pool_ = JitThreadPool::Create(
      "JIT thread pool",
      options->GetNumCompilerThreads());  // 默认为 1
  
  // 创建 JIT 编译器
  compiler_ = Compiler::Create(...);
  
  // 创建代码缓存
  code_cache_ = JitCodeCache::Create(...);
  
  return true;
}
```

### 6.2 启动与停止

```cpp
// art/runtime/jit/jit.cc

void Jit::Start() {
  Thread* self = Thread::Current();
  
  // 启动编译线程
  thread_pool_->StartWorkers(self);
}

void Jit::Stop() {
  Thread* self = Thread::Current();
  
  // 等待所有编译任务完成
  thread_pool_->Wait(self, /* do_work= */ false, /* may_hold_locks= */ false);
  
  // 停止工作线程
  thread_pool_->StopWorkers(self);
}
```

### 6.3 任务队列管理

```cpp
// art/runtime/thread_pool.cc

void ThreadPool::AddTask(Thread* self, Task* task) {
  MutexLock mu(self, task_queue_lock_);
  
  // 添加任务到队列
  task_queue_.push_back(task);
  
  // 唤醒等待的工作线程
  task_queue_condition_.Signal(self);
}

Task* ThreadPool::TakeTask(Thread* self) {
  MutexLock mu(self, task_queue_lock_);
  
  // 等待任务
  while (task_queue_.empty() && !shutting_down_) {
    task_queue_condition_.Wait(self);
  }
  
  if (shutting_down_) {
    return nullptr;
  }
  
  // 取出任务
  Task* task = task_queue_.front();
  task_queue_.pop_front();
  return task;
}
```

---

## 七、JitThreadPool vs 普通 ThreadPool

| 特性 | JitThreadPool | 普通 ThreadPool |
|-----|---------------|----------------|
| **用途** | 专门用于 JIT 编译 | 通用任务处理 |
| **线程数** | 通常 1-2 个 | 可配置多个 |
| **任务类型** | JitCompileTask | 任意 Task |
| **优先级** | 后台低优先级 | 可配置 |
| **生命周期** | 随 Runtime 创建/销毁 | 按需创建 |

---

## 八、性能考量

### 8.1 为什么默认只有 1 个编译线程？

```
┌─────────────────────────────────────────────────────────────────┐
│                     编译线程数量权衡                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  线程数过少：                    线程数过多：                     │
│  - 编译速度慢                   - CPU 资源竞争                   │
│  - 热点代码等待时间长            - 内存占用增加                   │
│                                 - 编译线程与应用线程争夺资源       │
│                                                                  │
│  权衡：1-2 个编译线程是最佳选择                                   │
│  - 不影响应用主线程              - 足够处理编译任务                │
│  - 低功耗                                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 编译策略

```cpp
// 不同场景下的编译策略

// 1. 前台应用：积极编译
if (is_foreground) {
  jit_threshold_ = 1000;  // 较低阈值，更快触发编译
}

// 2. 后台应用：保守编译
if (is_background) {
  jit_threshold_ = 10000;  // 较高阈值，减少编译
  thread_pool_->Pause();   // 暂停编译线程
}

// 3. 低电量：暂停编译
if (is_low_battery) {
  thread_pool_->StopWorkers();
}
```

---

## 九、调试与监控

### 9.1 查看 JIT 编译状态

```bash
# 查看 JIT 编译统计
adb shell dumpsys meminfo <package> | grep -i jit

# 查看 JIT 代码缓存
adb shell cmd package dump <package> | grep -i "jit"
```

### 9.2 JIT 相关系统属性

```bash
# 设置 JIT 阈值
adb shell setprop dalvik.vm.jit.codecachesize 4m

# 禁用 JIT（调试用）
adb shell setprop dalvik.vm.usejit false

# 设置编译线程数
adb shell setprop dalvik.vm.jitthreads 2
```

---

## 十、总结

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        JitThreadPool 总结                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. JitThreadPool 是 ART 中专门用于 JIT 编译的线程池                          │
│                                                                              │
│  2. 工作流程：                                                               │
│     热点检测 → 创建编译任务 → 加入队列 → Worker 执行 → 生成机器码              │
│                                                                              │
│  3. 特点：                                                                   │
│     - 异步编译，不阻塞主线程                                                  │
│     - 默认 1 个编译线程，平衡性能与资源                                        │
│     - 与 CodeCache 配合缓存编译结果                                           │
│                                                                              │
│  4. 核心类：                                                                 │
│     - ThreadPool: 基类                                                       │
│     - JitThreadPool: JIT 专用线程池                                          │
│     - ThreadPoolWorker: 工作线程                                             │
│     - JitCompileTask: 编译任务                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 参考资料

- ART 源码: `art/runtime/jit/`
- ThreadPool: `art/runtime/thread_pool.h`
- JIT: `art/runtime/jit/jit.cc`
