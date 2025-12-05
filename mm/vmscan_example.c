/*
 * 示例：在 mm_vmscan_direct_reclaim 函数中添加耗时日志
 * 
 * 这个文件展示了如何在内核的 mm_vmscan_direct_reclaim 函数中
 * 添加执行耗时统计和日志打印功能
 */

#include <linux/mm.h>
#include <linux/sched.h>
#include <linux/ktime.h>
#include <linux/timekeeping.h>
#include <linux/printk.h>

/**
 * mm_vmscan_direct_reclaim - 直接内存回收函数（带耗时统计）
 * @gfp_mask: 分配标志
 * @order: 分配阶数
 * @nid: 节点ID
 * @nodemask: 节点掩码
 * @may_writepage: 是否允许写回页面
 *
 * 执行直接内存回收操作，并在完成时打印耗时
 */
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
				       int nid, nodemask_t *nodemask,
				       bool may_writepage)
{
	ktime_t start_time, end_time;
	s64 duration_ns;
	unsigned long nr_reclaimed;

	/* 记录开始时间 */
	start_time = ktime_get();

	/* 原有的直接回收逻辑 */
	// ... 这里是你原有的内存回收代码 ...
	nr_reclaimed = 0; // 示例：实际应该调用原有的回收函数

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
