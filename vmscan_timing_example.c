/*
 * 示例：在 mm_vmscan_direct_reclaim 操作中添加耗时日志
 * 
 * 这个文件展示了如何在内核的 mm_vmscan_direct_reclaim 函数中添加耗时统计
 */

#include <linux/mm.h>
#include <linux/sched.h>
#include <linux/ktime.h>
#include <linux/timekeeping.h>
#include <linux/tracepoint.h>
#include <trace/events/mmflags.h>

/*
 * 方法1: 直接修改内核源码中的 mm_vmscan_direct_reclaim 函数
 * 
 * 在 mm/vmscan.c 文件中找到 mm_vmscan_direct_reclaim 函数，
 * 在函数开始和结束处添加时间戳记录
 */

unsigned long mm_vmscan_direct_reclaim_example(gfp_t gfp_mask, unsigned int order,
						int zonelist, nodemask_t *nodemask,
						int priority, struct scan_control *sc,
						unsigned long *nr_reclaimed)
{
	ktime_t start_time, end_time;
	s64 duration_ns;
	unsigned long ret;

	// 记录开始时间
	start_time = ktime_get();

	// 原有的直接回收逻辑
	// ... 这里是你原有的 mm_vmscan_direct_reclaim 代码 ...

	// 记录结束时间并计算耗时
	end_time = ktime_get();
	duration_ns = ktime_to_ns(ktime_sub(end_time, start_time));

	// 打印耗时日志
	// 使用 pr_info 打印到内核日志（dmesg）
	pr_info("mm_vmscan_direct_reclaim: pid=%d comm=%s order=%u priority=%d duration=%lld ns (%.3f ms)\n",
		current->pid, current->comm, order, priority,
		duration_ns, duration_ns / 1000000.0);

	// 或者使用 trace_printk（如果启用了 ftrace）
	trace_printk("mm_vmscan_direct_reclaim: duration=%lld ns\n", duration_ns);

	return ret;
}

/*
 * 方法2: 使用内核 tracepoint（推荐方法）
 * 
 * 在内核源码的适当位置添加 tracepoint，这样可以：
 * 1. 不修改核心逻辑代码
 * 2. 可以通过 ftrace/perf 等工具追踪
 * 3. 性能开销更小
 */

// 在 include/trace/events/vmscan.h 中添加（如果不存在）
// TRACE_EVENT(mm_vmscan_direct_reclaim_start,
// 	TP_PROTO(unsigned int order, int priority),
// 	TP_ARGS(order, priority),
// 	TP_STRUCT__entry(
// 		__field(unsigned int, order)
// 		__field(int, priority)
// 		__field(pid_t, pid)
// 		__array(char, comm, TASK_COMM_LEN)
// 	),
// 	TP_fast_assign(
// 		__entry->order = order;
// 		__entry->priority = priority;
// 		__entry->pid = current->pid;
// 		memcpy(__entry->comm, current->comm, TASK_COMM_LEN);
// 	),
// 	TP_printk("pid=%d comm=%s order=%u priority=%d",
// 		__entry->pid, __entry->comm, __entry->order, __entry->priority)
// );
//
// TRACE_EVENT(mm_vmscan_direct_reclaim_end,
// 	TP_PROTO(unsigned int order, int priority, s64 duration_ns),
// 	TP_ARGS(order, priority, duration_ns),
// 	TP_STRUCT__entry(
// 		__field(unsigned int, order)
// 		__field(int, priority)
// 		__field(s64, duration_ns)
// 		__field(pid_t, pid)
// 		__array(char, comm, TASK_COMM_LEN)
// 	),
// 	TP_fast_assign(
// 		__entry->order = order;
// 		__entry->priority = priority;
// 		__entry->duration_ns = duration_ns;
// 		__entry->pid = current->pid;
// 		memcpy(__entry->comm, current->comm, TASK_COMM_LEN);
// 	),
// 	TP_printk("pid=%d comm=%s order=%u priority=%d duration=%lld ns (%.3f ms)",
// 		__entry->pid, __entry->comm, __entry->order, __entry->priority,
// 		__entry->duration_ns, __entry->duration_ns / 1000000.0)
// );

/*
 * 方法3: 使用内核模块 hook（如果无法修改内核源码）
 * 
 * 创建一个内核模块，使用 kprobes 来 hook mm_vmscan_direct_reclaim 函数
 */

#ifdef CONFIG_KPROBES
#include <linux/kprobes.h>

static struct kprobe kp;
static ktime_t start_times[NR_CPUS]; // 每个CPU一个时间戳

static int handler_pre(struct kprobe *p, struct pt_regs *regs)
{
	int cpu = smp_processor_id();
	start_times[cpu] = ktime_get();
	return 0;
}

static void handler_post(struct kprobe *p, struct pt_regs *regs, unsigned long flags)
{
	int cpu = smp_processor_id();
	ktime_t end_time = ktime_get();
	s64 duration_ns = ktime_to_ns(ktime_sub(end_time, start_times[cpu]));

	pr_info("mm_vmscan_direct_reclaim: pid=%d comm=%s duration=%lld ns (%.3f ms)\n",
		current->pid, current->comm, duration_ns, duration_ns / 1000000.0);
}

static int __init vmscan_timing_init(void)
{
	kp.pre_handler = handler_pre;
	kp.post_handler = handler_post;
	kp.symbol_name = "mm_vmscan_direct_reclaim";

	if (register_kprobe(&kp) < 0) {
		pr_err("Failed to register kprobe\n");
		return -1;
	}

	pr_info("vmscan timing module loaded\n");
	return 0;
}

static void __exit vmscan_timing_exit(void)
{
	unregister_kprobe(&kp);
	pr_info("vmscan timing module unloaded\n");
}

module_init(vmscan_timing_init);
module_exit(vmscan_timing_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Track mm_vmscan_direct_reclaim timing");
#endif
