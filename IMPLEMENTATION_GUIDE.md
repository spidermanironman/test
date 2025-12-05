# mm_vmscan_direct_reclaim 耗时日志添加指南

## 概述

本文档说明如何在 Linux 内核的 `mm_vmscan_direct_reclaim` 函数中添加执行耗时统计和日志打印功能。

## 实现步骤

### 1. 定位函数位置

`mm_vmscan_direct_reclaim` 函数通常位于内核源码的 `mm/vmscan.c` 文件中。

### 2. 添加必要的头文件

在 `mm/vmscan.c` 文件顶部添加以下头文件：

```c
#include <linux/ktime.h>
#include <linux/timekeeping.h>
```

### 3. 修改函数实现

在函数开始处记录开始时间，在函数结束前记录结束时间并计算耗时：

```c
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
				       int nid, nodemask_t *nodemask,
				       bool may_writepage)
{
	ktime_t start_time, end_time;
	s64 duration_ns;
	unsigned long nr_reclaimed;

	/* 记录开始时间 */
	start_time = ktime_get();

	/* 原有的内存回收逻辑 */
	// ... 原有代码 ...

	/* 记录结束时间并计算耗时 */
	end_time = ktime_get();
	duration_ns = ktime_to_ns(ktime_sub(end_time, start_time));

	/* 打印耗时日志 */
	pr_info("mm_vmscan_direct_reclaim: completed in %lld ns (%lld.%03lld ms), "
		"gfp_mask=0x%x, order=%d, nid=%d, reclaimed=%lu pages\n",
		duration_ns,
		duration_ns / NSEC_PER_MSEC,
		(duration_ns % NSEC_PER_MSEC) / NSEC_PER_USEC,
		gfp_mask, order, nid, nr_reclaimed);

	return nr_reclaimed;
}
```

## 关键点说明

### 时间测量 API

- **`ktime_get()`**: 获取当前时间（高精度，纳秒级）
- **`ktime_sub()`**: 计算时间差
- **`ktime_to_ns()`**: 将时间差转换为纳秒

### 日志打印

- **`pr_info()`**: 内核信息级别日志，会输出到内核日志缓冲区
- 可以通过 `dmesg` 或 `/var/log/kern.log` 查看日志

### 时间单位转换

- `NSEC_PER_MSEC`: 每毫秒的纳秒数 (1,000,000)
- `NSEC_PER_USEC`: 每微秒的纳秒数 (1,000)
- 日志中同时显示纳秒和毫秒，便于阅读

## 日志输出示例

添加日志后，当函数执行时会输出类似以下格式的日志：

```
mm_vmscan_direct_reclaim: completed in 1234567 ns (1.234 ms), gfp_mask=0x3d0, order=0, nid=0, reclaimed=42 pages
```

## 查看日志

### 方法1: 使用 dmesg
```bash
dmesg | grep mm_vmscan_direct_reclaim
```

### 方法2: 查看内核日志文件
```bash
tail -f /var/log/kern.log | grep mm_vmscan_direct_reclaim
```

### 方法3: 使用 journalctl (systemd 系统)
```bash
journalctl -k | grep mm_vmscan_direct_reclaim
```

## 性能考虑

- `ktime_get()` 是轻量级操作，开销很小
- 如果担心性能影响，可以考虑：
  - 使用条件编译（`#ifdef CONFIG_DEBUG_VMSCAN`）
  - 使用 tracepoint 替代 pr_info（更高效）
  - 添加采样机制（只记录部分调用）

## 高级选项：使用 Tracepoint

如果需要更高效的日志记录，可以考虑使用内核 tracepoint：

```c
#include <trace/events/vmscan.h>

trace_mm_vmscan_direct_reclaim_start(gfp_mask, order);
// ... 原有代码 ...
trace_mm_vmscan_direct_reclaim_end(nr_reclaimed, duration_ns);
```

然后通过 `ftrace` 或 `perf` 工具来查看和分析。

## 注意事项

1. 确保在内核配置中启用了 `CONFIG_PRINTK`
2. 日志级别可能需要调整（`/proc/sys/kernel/printk`）
3. 在高频调用的路径上，过多的日志可能影响性能
4. 建议在开发/调试阶段使用，生产环境可以考虑使用 tracepoint
