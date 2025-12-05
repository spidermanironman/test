/*
 * AOSP 内核 mm/vmscan.c 修改示例
 * 文件路径: kernel/common/mm/vmscan.c
 * 
 * 在 mm_vmscan_direct_reclaim 函数中添加耗时日志
 */

// ============================================
// 1. 确保文件头部包含必要的头文件
// ============================================
// 在 mm/vmscan.c 文件头部添加（如果不存在）：
#include <linux/ktime.h>
#include <linux/sched.h>
#include <linux/sched/task.h>

// ============================================
// 2. 修改 mm_vmscan_direct_reclaim 函数
// ============================================
// 查找函数定义位置，通常在 mm/vmscan.c 中

/*
 * 修改前（示例）：
 */
unsigned long mm_vmscan_direct_reclaim_OLD(gfp_t gfp_mask, int order,
				       struct zonelist *zonelist,
				       nodemask_t *nodemask,
				       int priority, struct scan_control *sc)
{
	unsigned long nr_reclaimed = 0;
	
	// ... 原有的 direct reclaim 逻辑 ...
	
	return nr_reclaimed;
}

/*
 * 修改后：
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
	
	// ========== 添加：记录开始时间 ==========
	start_time = ktime_get();
	
	// ... 原有的 direct reclaim 逻辑保持不变 ...
	// 例如：
	// sc->gfp_mask = gfp_mask;
	// sc->order = order;
	// sc->priority = priority;
	// nr_reclaimed = do_try_to_free_pages(zonelist, sc);
	
	// ========== 添加：计算耗时并打印日志 ==========
	end_time = ktime_get();
	duration_us = ktime_to_us(ktime_sub(end_time, start_time));
	duration_ms = (unsigned long)(duration_us / 1000);
	
	// 打印耗时日志
	// 选项1: 使用 pr_info（推荐，会输出到 dmesg）
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
	
	// 选项2: 使用 pr_debug（需要启用 CONFIG_DYNAMIC_DEBUG）
	// pr_debug("direct_reclaim: pid=%d comm=%s duration=%lu ms order=%d reclaimed=%lu\n",
	// 	current->pid, current->comm, duration_ms, order, nr_reclaimed);
	
	// 选项3: 使用 trace_printk（用于 ftrace）
	// trace_printk("direct_reclaim: pid=%d duration=%lu us\n", 
	// 	current->pid, duration_us);
	
	return nr_reclaimed;
}

// ============================================
// 3. 如果使用 tracepoint（高级方案）
// ============================================
// 文件路径: kernel/common/include/trace/events/vmscan.h
// 添加以下 tracepoint 定义：

/*
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
*/

// 然后在 vmscan.c 中使用：
// #include <trace/events/vmscan.h>
// trace_direct_reclaim_duration(duration_us, order, priority, 
// 			      nr_reclaimed, current->pid, current->comm);
