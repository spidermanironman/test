/*
 * 内核模块：监控 mm_vmscan_direct_reclaim 操作的耗时
 * 
 * 编译方法：
 *   make -C /lib/modules/$(uname -r)/build M=$(pwd) modules
 * 
 * 加载模块：
 *   sudo insmod vmscan_timing_module.ko
 * 
 * 查看日志：
 *   dmesg | tail -f
 *   或
 *   sudo tail -f /var/log/kern.log
 * 
 * 卸载模块：
 *   sudo rmmod vmscan_timing_module
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/kprobes.h>
#include <linux/ktime.h>
#include <linux/sched.h>
#include <linux/slab.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Your Name");
MODULE_DESCRIPTION("Monitor mm_vmscan_direct_reclaim operation duration");
MODULE_VERSION("1.0");

#define MAX_CONCURRENT 100

struct timing_entry {
	ktime_t start_time;
	pid_t pid;
	unsigned int order;
	int priority;
};

static struct kprobe kp;
static struct timing_entry *timing_entries;

/* kprobe 前置处理函数：记录开始时间 */
static int handler_pre(struct kprobe *p, struct pt_regs *regs)
{
	struct timing_entry *entry;
	pid_t pid = current->pid;
	int idx = pid % MAX_CONCURRENT;

	entry = &timing_entries[idx];
	entry->start_time = ktime_get();
	entry->pid = pid;
	
	/* 从寄存器中提取参数（x86_64架构） */
	/* order 通常在 rsi 寄存器（第二个参数） */
	/* priority 通常在 rcx 寄存器（第四个参数） */
	/* 注意：这依赖于具体的函数调用约定，可能需要调整 */
	
	return 0;
}

/* kprobe 后置处理函数：计算并打印耗时 */
static void handler_post(struct kprobe *p, struct pt_regs *regs, unsigned long flags)
{
	struct timing_entry *entry;
	ktime_t end_time;
	s64 duration_ns;
	pid_t pid = current->pid;
	int idx = pid % MAX_CONCURRENT;

	entry = &timing_entries[idx];
	
	/* 检查是否是同一个进程的调用 */
	if (entry->pid != pid || entry->start_time == 0)
		return;

	end_time = ktime_get();
	duration_ns = ktime_to_ns(ktime_sub(end_time, entry->start_time));

	/* 打印耗时日志 */
	pr_info("mm_vmscan_direct_reclaim: pid=%d comm=%s duration=%lld ns (%.3f ms)\n",
		pid, current->comm, duration_ns, duration_ns / 1000000.0);

	/* 如果耗时超过阈值，打印警告 */
	if (duration_ns > 100000000) { /* 100ms */
		pr_warn("mm_vmscan_direct_reclaim: SLOW operation detected! pid=%d duration=%.3f ms\n",
			pid, duration_ns / 1000000.0);
	}

	/* 清除时间戳 */
	entry->start_time = 0;
}

/* 错误处理函数 */
static int handler_fault(struct kprobe *p, struct pt_regs *regs, int trapnr)
{
	pr_err("kprobe fault at %p\n", p->addr);
	return 0;
}

static int __init vmscan_timing_init(void)
{
	int ret;

	/* 分配内存存储时间戳 */
	timing_entries = kmalloc(sizeof(struct timing_entry) * MAX_CONCURRENT, GFP_KERNEL);
	if (!timing_entries) {
		pr_err("Failed to allocate memory for timing entries\n");
		return -ENOMEM;
	}

	memset(timing_entries, 0, sizeof(struct timing_entry) * MAX_CONCURRENT);

	/* 设置 kprobe */
	kp.pre_handler = handler_pre;
	kp.post_handler = handler_post;
	kp.fault_handler = handler_fault;
	kp.symbol_name = "mm_vmscan_direct_reclaim";

	/* 注册 kprobe */
	ret = register_kprobe(&kp);
	if (ret < 0) {
		pr_err("Failed to register kprobe for mm_vmscan_direct_reclaim: %d\n", ret);
		kfree(timing_entries);
		return ret;
	}

	pr_info("vmscan_timing_module: kprobe registered at %p\n", kp.addr);
	pr_info("vmscan_timing_module: Monitoring mm_vmscan_direct_reclaim operations\n");
	
	return 0;
}

static void __exit vmscan_timing_exit(void)
{
	unregister_kprobe(&kp);
	kfree(timing_entries);
	pr_info("vmscan_timing_module: Unloaded\n");
}

module_init(vmscan_timing_init);
module_exit(vmscan_timing_exit);
