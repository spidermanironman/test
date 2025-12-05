# AOSP mm_vmscan_direct_reclaim 耗时日志 - 完整修改总结

## 📋 修改概览

在AOSP内核中为 `mm_vmscan_direct_reclaim` 函数添加耗时统计和日志打印功能。

---

## 📁 需要修改的文件

### 主文件
**路径**: `kernel/common/mm/vmscan.c`

**说明**: 这是内存回收（vmscan）的核心实现文件，包含直接内存回收函数。

---

## 🔧 具体修改点

### 修改点 1: 添加头文件包含

**文件**: `kernel/common/mm/vmscan.c`  
**位置**: 文件头部，`#include` 语句区域（约第20-50行）  
**操作**: 添加以下头文件（如果不存在）

```c
#include <linux/trace_clock.h>  // 用于 local_clock() 函数
```

**注意**: 
- `linux/sched.h` 和 `linux/time.h` 通常已经包含
- 如果已存在则无需重复添加

---

### 修改点 2: 在函数开始处添加时间记录变量

**文件**: `kernel/common/mm/vmscan.c`  
**位置**: `mm_vmscan_direct_reclaim` 函数内部，变量声明区域  
**函数签名**: 
```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
                                       struct zonelist *zonelist,
                                       nodemask_t *nodemask,
                                       int alloc_flags, struct alloc_context *ac)
```

**添加代码**:
```c
    u64 start_time, end_time, duration_ns;
    unsigned long duration_ms;
```

**位置示例**:
```c
unsigned long mm_vmscan_direct_reclaim(...)
{
    unsigned long nr_reclaimed;
    u64 start_time, end_time, duration_ns;        // ← 添加这里
    unsigned long duration_ms;                     // ← 添加这里
    
    start_time = local_clock();                    // ← 修改点3
    // ... 原有代码 ...
}
```

---

### 修改点 3: 记录函数开始执行时间

**文件**: `kernel/common/mm/vmscan.c`  
**位置**: 在修改点2之后，原有函数逻辑之前  
**添加代码**:
```c
    // 记录开始时间
    start_time = local_clock();
```

---

### 修改点 4: 计算耗时并打印日志

**文件**: `kernel/common/mm/vmscan.c`  
**位置**: 在函数返回语句之前（`return nr_reclaimed;` 之前）  
**添加代码**:
```c
    // 记录结束时间并计算耗时
    end_time = local_clock();
    duration_ns = end_time - start_time;
    duration_ms = duration_ns / NSEC_PER_MSEC;
    
    // 打印耗时日志
    trace_printk("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, gfp_mask=0x%x, reclaimed=%lu pages, pid=%d, comm=%s\n",
                 duration_ms, order, gfp_mask, nr_reclaimed, current->pid, current->comm);
```

---

## 📝 完整代码示例

### 修改前
```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
                                       struct zonelist *zonelist,
                                       nodemask_t *nodemask,
                                       int alloc_flags, struct alloc_context *ac)
{
    unsigned long nr_reclaimed;
    
    // ... 原有实现代码 ...
    
    return nr_reclaimed;
}
```

### 修改后
```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
                                       struct zonelist *zonelist,
                                       nodemask_t *nodemask,
                                       int alloc_flags, struct alloc_context *ac)
{
    unsigned long nr_reclaimed;
    u64 start_time, end_time, duration_ns;
    unsigned long duration_ms;
    
    // 记录开始时间
    start_time = local_clock();
    
    // ... 原有实现代码保持不变 ...
    
    // 记录结束时间并计算耗时
    end_time = local_clock();
    duration_ns = end_time - start_time;
    duration_ms = duration_ns / NSEC_PER_MSEC;
    
    // 打印耗时日志
    trace_printk("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, gfp_mask=0x%x, reclaimed=%lu pages, pid=%d, comm=%s\n",
                 duration_ms, order, gfp_mask, nr_reclaimed, current->pid, current->comm);
    
    return nr_reclaimed;
}
```

---

## 🔍 如何查找函数位置

### 方法1: 使用 grep 搜索
```bash
cd kernel/common
grep -n "mm_vmscan_direct_reclaim" mm/vmscan.c
```

### 方法2: 使用 ctags/cscope
```bash
cd kernel/common
cscope -d -L1 mm_vmscan_direct_reclaim
```

### 方法3: 直接查看文件
```bash
cd kernel/common
vim mm/vmscan.c
# 然后搜索: /mm_vmscan_direct_reclaim
```

---

## ✅ 验证和测试

### 1. 编译内核
```bash
cd kernel/common
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-android- vmlinux
# 或根据你的平台调整
```

### 2. 查看日志输出

**方法A: 使用 dmesg**
```bash
adb shell dmesg | grep "mm_vmscan_direct_reclaim"
```

**方法B: 使用 trace**
```bash
adb shell
echo 1 > /sys/kernel/debug/tracing/tracing_on
cat /sys/kernel/debug/tracing/trace | grep "mm_vmscan_direct_reclaim"
```

**方法C: 使用 logcat（如果使用 pr_info）**
```bash
adb logcat | grep "mm_vmscan_direct_reclaim"
```

### 3. 预期输出格式
```
mm_vmscan_direct_reclaim: duration=15 ms, order=0, gfp_mask=0x140dca, reclaimed=32 pages, pid=1234, comm=system_server
```

---

## ⚠️ 注意事项

1. **多返回点处理**: 如果函数有多个 `return` 语句，需要统一处理
   - 方案A: 使用 `goto` 跳转到统一的日志打印位置
   - 方案B: 在每个返回点前都添加日志代码

2. **日志方式选择**:
   - `trace_printk`: 需要启用内核trace功能，性能开销小
   - `pr_info`: 更通用，但可能产生较多日志

3. **性能影响**: 添加时间记录和日志打印会有轻微性能开销，通常可接受

4. **编译依赖**: 确保内核配置中启用了相应的功能
   - `CONFIG_TRACING=y`
   - `CONFIG_FTRACE=y` (如果使用trace_printk)

---

## 📚 相关文件参考

- **主文件**: `kernel/common/mm/vmscan.c`
- **头文件**:
  - `kernel/common/include/linux/sched.h` - 进程信息
  - `kernel/common/include/linux/time.h` - 时间定义
  - `kernel/common/include/linux/trace_clock.h` - 时间戳函数
  - `kernel/common/include/linux/mm.h` - 内存管理定义

---

## 🛠️ 应用补丁

如果使用提供的 patch 文件：

```bash
cd kernel/common
git apply /path/to/add_direct_reclaim_timing.patch
```

或者手动应用修改。

---

## 📊 日志信息说明

打印的日志包含以下信息：
- `duration`: 耗时（毫秒）
- `order`: 分配阶数
- `gfp_mask`: 分配标志位
- `reclaimed`: 回收的页数
- `pid`: 进程ID
- `comm`: 进程名称

这些信息有助于分析内存回收的性能和调用上下文。
