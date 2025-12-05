# AOSP mm_vmscan_direct_reclaim 耗时日志 - 修改清单

## 修改文件
**文件路径**: `kernel/common/mm/vmscan.c`

## 具体修改点

### 修改点1: 文件头部 - 添加头文件（约第20-30行附近）

**位置**: 在文件开头的 `#include` 语句区域

**添加内容**:
```c
#include <linux/sched.h>
#include <linux/time.h>
#include <linux/trace_clock.h>
```

**检查**: 如果这些头文件已经存在，则跳过

---

### 修改点2: mm_vmscan_direct_reclaim 函数 - 添加时间变量（函数开始处）

**位置**: 在 `mm_vmscan_direct_reclaim` 函数内部，变量声明区域（函数第一行之后）

**查找函数签名**:
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

---

### 修改点3: mm_vmscan_direct_reclaim 函数 - 记录开始时间

**位置**: 在修改点2之后，原有函数逻辑之前

**添加代码**:
```c
    // 记录开始时间
    start_time = local_clock();
```

---

### 修改点4: mm_vmscan_direct_reclaim 函数 - 计算耗时并打印日志

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

## 完整修改示例（最小改动版本）

在 `mm_vmscan_direct_reclaim` 函数中：

**原代码**:
```c
unsigned long mm_vmscan_direct_reclaim(...)
{
    unsigned long nr_reclaimed;
    
    // ... 原有代码 ...
    
    return nr_reclaimed;
}
```

**修改后**:
```c
unsigned long mm_vmscan_direct_reclaim(...)
{
    unsigned long nr_reclaimed;
    u64 start_time, end_time, duration_ns;
    unsigned long duration_ms;
    
    start_time = local_clock();
    
    // ... 原有代码保持不变 ...
    
    end_time = local_clock();
    duration_ns = end_time - start_time;
    duration_ms = duration_ns / NSEC_PER_MSEC;
    
    trace_printk("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, gfp_mask=0x%x, reclaimed=%lu pages, pid=%d, comm=%s\n",
                 duration_ms, order, gfp_mask, nr_reclaimed, current->pid, current->comm);
    
    return nr_reclaimed;
}
```

---

## 验证步骤

1. **编译内核**:
   ```bash
   cd kernel/common
   make
   ```

2. **刷入设备并查看日志**:
   ```bash
   adb shell dmesg | grep "mm_vmscan_direct_reclaim"
   ```

3. **或者使用trace**:
   ```bash
   adb shell
   echo 1 > /sys/kernel/debug/tracing/tracing_on
   cat /sys/kernel/debug/tracing/trace | grep "mm_vmscan_direct_reclaim"
   ```

---

## 注意事项

- 如果函数有多个 `return` 语句，需要统一处理（使用 `goto` 或内联函数）
- `trace_printk` 需要内核trace功能启用
- 如果 `trace_printk` 不可用，可以使用 `pr_info` 替代
- 时间精度为纳秒级，转换为毫秒显示

---

## 相关定义位置

- `NSEC_PER_MSEC`: `kernel/common/include/linux/time.h` 或 `kernel/common/include/linux/time64.h`
- `local_clock()`: `kernel/common/include/linux/trace_clock.h`
- `current`: `kernel/common/include/linux/sched.h`
