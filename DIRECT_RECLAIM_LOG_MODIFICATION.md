# AOSP 内核 Direct Reclaim 耗时日志添加方案

## 概述
在应用线程执行 `mm_vmscan_direct_reclaim` 操作完成时，添加耗时日志输出。

## 修改文件列表

### 1. 主要修改文件：`mm/vmscan.c`

**文件路径：** `kernel/common/mm/vmscan.c` 或 `mm/vmscan.c`

**修改位置：** `mm_vmscan_direct_reclaim` 函数

**修改说明：**
- 在函数开始处记录开始时间
- 在函数结束处计算耗时并打印日志

---

## 详细修改点

### 修改点 1：在 `mm/vmscan_direct_reclaim` 函数中添加时间记录

**位置：** `mm/vmscan_direct_reclaim` 函数内部

**修改前：**
```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
				       struct zonelist *zonelist,
				       nodemask_t *nodemask,
				       int priority, struct scan_control *sc)
{
	unsigned long nr_reclaimed = 0;
	// ... 原有代码 ...
}
```

**修改后：**
```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
				       struct zonelist *zonelist,
				       nodemask_t *nodemask,
				       int priority, struct scan_control *sc)
{
	unsigned long nr_reclaimed = 0;
	ktime_t start_time, end_time;
	s64 duration_us;  // 微秒
	unsigned long duration_ms;  // 毫秒
	
	// 记录开始时间
	start_time = ktime_get();
	
	// ... 原有代码保持不变 ...
	
	// 在函数返回前计算耗时并打印日志
	end_time = ktime_get();
	duration_us = ktime_to_us(ktime_sub(end_time, start_time));
	duration_ms = duration_us / 1000;
	
	// 打印耗时日志（使用 pr_info 或 trace_printk）
	if (duration_ms > 0 || duration_us > 0) {
		pr_info("direct_reclaim: pid=%d comm=%s duration=%lu ms (%lld us) order=%d priority=%d reclaimed=%lu pages\n",
			current->pid, current->comm, duration_ms, duration_us,
			order, priority, nr_reclaimed);
	}
	
	return nr_reclaimed;
}
```

---

### 修改点 2：确保包含必要的头文件

**位置：** `mm/vmscan.c` 文件头部

**检查并添加（如果缺失）：**
```c
#include <linux/ktime.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
```

---

## 完整代码示例

以下是 `mm/vmscan.c` 中 `mm_vmscan_direct_reclaim` 函数的完整修改示例：

```c
/**
 * mm_vmscan_direct_reclaim - 直接内存回收
 * @gfp_mask: 分配标志
 * @order: 分配阶数
 * @zonelist: 区域列表
 * @nodemask: 节点掩码
 * @priority: 优先级
 * @sc: 扫描控制结构
 *
 * 返回：回收的页数
 */
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
				       struct zonelist *zonelist,
				       nodemask_t *nodemask,
				       int priority, struct scan_control *sc)
{
	unsigned long nr_reclaimed = 0;
	ktime_t start_time, end_time;
	s64 duration_us;
	unsigned long duration_ms;
	
	// 记录开始时间
	start_time = ktime_get();
	
	// 原有的 direct reclaim 逻辑
	// ... 原有代码 ...
	
	// 在函数返回前添加耗时统计
	end_time = ktime_get();
	duration_us = ktime_to_us(ktime_sub(end_time, start_time));
	duration_ms = (unsigned long)(duration_us / 1000);
	
	// 打印耗时日志
	if (duration_ms > 0 || duration_us > 0) {
		pr_info("direct_reclaim: pid=%d comm=%s duration=%lu ms (%lld us) order=%d priority=%d reclaimed=%lu pages gfp_mask=0x%x\n",
			current->pid,
			current->comm,
			duration_ms,
			duration_us,
			order,
			priority,
			nr_reclaimed,
			gfp_mask);
	}
	
	return nr_reclaimed;
}
```

---

## 替代方案：使用 tracepoint

如果需要更专业的性能追踪，可以使用 tracepoint：

### 修改点 3：添加 tracepoint（可选）

**位置：** `include/trace/events/vmscan.h` 或创建新的 tracepoint

**添加 tracepoint 定义：**
```c
TRACE_EVENT(direct_reclaim_duration,
	TP_PROTO(unsigned long duration_us, int order, int priority, 
		 unsigned long nr_reclaimed, pid_t pid, char *comm),
	TP_ARGS(duration_us, order, priority, nr_reclaimed, pid, comm),
	TP_STRUCT__entry(
		__field(unsigned long, duration_us)
		__field(int, order)
		__field(int, priority)
		__field(unsigned long, nr_reclaimed)
		__field(pid_t, pid)
		__string(comm, comm)
	),
	TP_fast_assign(
		__entry->duration_us = duration_us;
		__entry->order = order;
		__entry->priority = priority;
		__entry->nr_reclaimed = nr_reclaimed;
		__entry->pid = pid;
		__assign_str(comm, comm);
	),
	TP_printk("pid=%d comm=%s duration=%lu us order=%d priority=%d reclaimed=%lu pages",
		__entry->pid, __get_str(comm), __entry->duration_us,
		__entry->order, __entry->priority, __entry->nr_reclaimed)
);
```

**在 vmscan.c 中使用：**
```c
#include <trace/events/vmscan.h>

// 在函数返回前
trace_direct_reclaim_duration(duration_us, order, priority, 
			      nr_reclaimed, current->pid, current->comm);
```

---

## 编译和验证

1. **编译内核：**
   ```bash
   cd kernel/common
   make ARCH=arm64 CROSS_COMPILE=aarch64-linux-android- menuconfig
   # 确保 CONFIG_PRINTK=y
   make ARCH=arm64 CROSS_COMPILE=aarch64-linux-android-
   ```

2. **查看日志：**
   ```bash
   adb shell dmesg | grep direct_reclaim
   # 或
   adb logcat | grep direct_reclaim
   ```

---

## 注意事项

1. **性能影响：** `ktime_get()` 和日志打印本身有开销，在高频调用场景下可能影响性能
2. **日志级别：** 使用 `pr_info` 会输出到 dmesg，如果日志过多可考虑使用 `pr_debug` 并启用 `CONFIG_DYNAMIC_DEBUG`
3. **时间精度：** `ktime_get()` 提供纳秒级精度，转换为微秒或毫秒显示
4. **线程信息：** `current->pid` 和 `current->comm` 可以标识是哪个进程/线程触发的回收

---

## 文件路径总结

| 文件 | 路径 | 修改类型 |
|------|------|----------|
| 主要修改 | `kernel/common/mm/vmscan.c` | 添加时间记录和日志 |
| 头文件检查 | `kernel/common/mm/vmscan.c` | 确保包含 ktime.h 等 |
| Tracepoint（可选）| `kernel/common/include/trace/events/vmscan.h` | 添加 tracepoint 定义 |
