/*
 * AOSP mm/vmscan.c 修改示例
 * 为 mm_vmscan_direct_reclaim 函数添加耗时日志
 * 
 * 文件路径: kernel/common/mm/vmscan.c
 */

// ============================================
// 修改点1: 确保头文件包含（在文件顶部）
// ============================================
// 在 vmscan.c 文件的开头部分，确保包含以下头文件：
#include <linux/sched.h>        // 用于 current->pid, current->comm
#include <linux/time.h>          // 用于时间相关函数
#include <linux/trace_clock.h>   // 用于 local_clock()
#include <linux/ktime.h>         // 用于时间计算

// ============================================
// 修改点2: mm_vmscan_direct_reclaim 函数修改
// ============================================

// 原始函数签名（示例，实际可能略有不同）
unsigned long mm_vmscan_direct_reclaim(gfp_t gfp_mask, int order,
                                       struct zonelist *zonelist,
                                       nodemask_t *nodemask,
                                       int alloc_flags, struct alloc_context *ac)
{
    unsigned long nr_reclaimed;
    
    // ========== 添加开始 ==========
    // 添加时间记录变量
    u64 start_time, end_time, duration_ns;
    unsigned long duration_ms;
    // ========== 添加结束 ==========
    
    // ========== 添加开始 ==========
    // 记录函数开始执行时间
    start_time = local_clock();
    // ========== 添加结束 ==========
    
    // ... 原有的函数实现代码保持不变 ...
    // 例如：
    // nr_reclaimed = do_try_to_free_pages(...);
    // 或其他内存回收逻辑
    
    // ========== 添加开始 ==========
    // 记录函数结束时间并计算耗时
    end_time = local_clock();
    duration_ns = end_time - start_time;
    duration_ms = duration_ns / NSEC_PER_MSEC;
    
    // 打印耗时日志（方案1: 使用 trace_printk）
    trace_printk("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, "
                 "gfp_mask=0x%x, reclaimed=%lu pages, pid=%d, comm=%s\n",
                 duration_ms, order, gfp_mask, nr_reclaimed, 
                 current->pid, current->comm);
    
    // 或者使用 pr_info（方案2: 更通用的日志方式）
    // pr_info("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, "
    //         "gfp_mask=0x%x, reclaimed=%lu pages, pid=%d, comm=%s\n",
    //         duration_ms, order, gfp_mask, nr_reclaimed,
    //         current->pid, current->comm);
    // ========== 添加结束 ==========
    
    return nr_reclaimed;
}

// ============================================
// 修改点3: 如果函数有多个返回点，使用统一处理
// ============================================

// 如果原函数有多个返回点，建议重构为：
unsigned long mm_vmscan_direct_reclaim_v2(gfp_t gfp_mask, int order,
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
    
    // 在函数末尾统一处理日志（所有返回都通过这里）
    end_time = local_clock();
    duration_ns = end_time - start_time;
    duration_ms = duration_ns / NSEC_PER_MSEC;
    
    trace_printk("mm_vmscan_direct_reclaim: duration=%lu ms, order=%d, "
                 "gfp_mask=0x%x, reclaimed=%lu pages, pid=%d, comm=%s\n",
                 duration_ms, order, gfp_mask, nr_reclaimed,
                 current->pid, current->comm);
    
    return nr_reclaimed;
}

// ============================================
// 修改点4: 更详细的日志版本（可选）
// ============================================

unsigned long mm_vmscan_direct_reclaim_detailed(gfp_t gfp_mask, int order,
                                                 struct zonelist *zonelist,
                                                 nodemask_t *nodemask,
                                                 int alloc_flags, struct alloc_context *ac)
{
    unsigned long nr_reclaimed;
    u64 start_time, end_time, duration_ns;
    unsigned long duration_ms, duration_us;
    struct timespec64 start_ts, end_ts;
    
    // 记录开始时间（多种方式）
    start_time = local_clock();
    ktime_get_ts64(&start_ts);
    
    // ... 原有实现代码 ...
    
    // 记录结束时间
    end_time = local_clock();
    ktime_get_ts64(&end_ts);
    duration_ns = end_time - start_time;
    duration_ms = duration_ns / NSEC_PER_MSEC;
    duration_us = duration_ns / NSEC_PER_USEC;
    
    // 详细日志输出
    trace_printk("mm_vmscan_direct_reclaim: "
                 "duration=%lu ms (%lu us, %llu ns), "
                 "order=%d, gfp_mask=0x%x, "
                 "reclaimed=%lu pages, "
                 "pid=%d, tgid=%d, comm=%s, "
                 "start_time=%lld, end_time=%lld\n",
                 duration_ms, duration_us, duration_ns,
                 order, gfp_mask, nr_reclaimed,
                 current->pid, current->tgid, current->comm,
                 start_time, end_time);
    
    return nr_reclaimed;
}
