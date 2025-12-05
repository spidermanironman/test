# AOSP mm_vmscan_direct_reclaim 耗时日志添加方案

## 概述
在AOSP内核中为`mm_vmscan_direct_reclaim`函数添加耗时统计和日志打印功能。

## 修改文件路径
**文件路径**: `kernel/common/mm/vmscan.c`

## 修改位置和代码

### 1. 在文件头部添加必要的头文件（如果还没有）

在`vmscan.c`文件的开头部分，确保包含以下头文件：

```c
#include <linux/sched.h>
#include <linux/time.h>
#include <linux/trace_clock.h>
```

### 2. 修改 `mm_vmscan_direct_reclaim` 函数

找到`mm_vmscan_direct_reclaim`函数（通常在`vmscan.c`文件中），函数签名类似：

```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
                                       struct zonelist *zonelist,
                                       nodemask_t *nodemask,
                                       int alloc_flags, struct alloc_context *ac)
```

**修改点1**: 在函数开始处添加时间记录

在函数的第一行（变量声明之后）添加：

```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
                                       struct zonelist *zonelist,
                                       nodemask_t *nodemask,
                                       int alloc_flags, struct alloc_context *ac)
{
    unsigned long nr_reclaimed;
    u64 start_time, end_time, duration_ns;
    struct timespec64 start_ts, end_ts;
    
    // 记录开始时间
    start_time = local_clock();
    ktime_get_ts64(&start_ts);
    
    // ... 原有代码 ...
```

**修改点2**: 在函数返回前添加耗时计算和日志打印

在函数的所有返回语句之前（或使用goto统一处理），添加：

```c
    // 记录结束时间
    end_time = local_clock();
    ktime_get_ts64(&end_ts);
    duration_ns = end_time - start_time;
    
    // 计算耗时（毫秒）
    unsigned long duration_ms = duration_ns / NSEC_PER_MSEC;
    
    // 打印日志
    trace_printk("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, gfp_mask=0x%x, reclaimed=%lu pages\n",
                 duration_ms, order, gfp_mask, nr_reclaimed);
    
    // 或者使用 pr_info（如果trace_printk不可用）
    // pr_info("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, gfp_mask=0x%x, reclaimed=%lu pages\n",
    //         duration_ms, order, gfp_mask, nr_reclaimed);
    
    return nr_reclaimed;
}
```

## 完整修改示例

### 修改前（示例）:
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

### 修改后:
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
    
    // ... 原有实现代码 ...
    
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

## 注意事项

1. **时间精度**: 使用`local_clock()`获取纳秒级精度的时间戳
2. **性能影响**: 添加时间记录和日志打印会有轻微的性能开销，但通常可以接受
3. **日志级别**: 
   - `trace_printk`: 需要启用内核trace功能才能看到
   - `pr_info`: 会在dmesg中显示，但可能产生较多日志
4. **多返回点处理**: 如果函数有多个返回点，建议使用goto统一处理日志打印
5. **编译配置**: 确保内核配置中启用了相应的日志功能

## 查看日志

### 方法1: 使用dmesg
```bash
adb shell dmesg | grep "mm_vmscan_direct_reclaim"
```

### 方法2: 使用trace
```bash
adb shell
echo 1 > /sys/kernel/debug/tracing/tracing_on
cat /sys/kernel/debug/tracing/trace | grep "mm_vmscan_direct_reclaim"
```

### 方法3: 使用logcat（如果使用pr_info）
```bash
adb logcat | grep "mm_vmscan_direct_reclaim"
```

## 替代方案：使用ftrace

如果需要更详细的跟踪，可以考虑使用ftrace功能：

1. 在函数入口和出口添加tracepoint
2. 使用`trace_direct_reclaim_start`和`trace_direct_reclaim_end`
3. 通过ftrace工具分析耗时

## 相关文件位置参考

- **主要修改文件**: `kernel/common/mm/vmscan.c`
- **头文件位置**: 
  - `kernel/common/include/linux/sched.h`
  - `kernel/common/include/linux/time.h`
  - `kernel/common/include/linux/trace_clock.h`
  - `kernel/common/include/linux/mm.h`
