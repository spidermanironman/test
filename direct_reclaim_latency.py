#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接内存回收（Direct Reclaim）延迟追踪工具

使用 eBPF 追踪 mm_vmscan_direct_reclaim_begin 和 mm_vmscan_direct_reclaim_end
tracepoint，计算并打印每次直接回收操作的耗时。

使用方法:
    sudo python3 direct_reclaim_latency.py

需要安装 bcc 工具包:
    Ubuntu/Debian: sudo apt-get install bpfcc-tools python3-bpfcc
    CentOS/RHEL:   sudo yum install bcc-tools python3-bcc
"""

from bcc import BPF
from time import strftime
import argparse

# eBPF 程序
bpf_text = """
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

struct start_data_t {
    u64 ts;
    int order;
    int gfp_flags;
};

struct event_t {
    u32 pid;
    u32 tgid;
    char comm[TASK_COMM_LEN];
    u64 delta_us;      // 耗时（微秒）
    int order;         // 内存分配 order
    unsigned long nr_reclaimed;  // 回收的页面数
};

BPF_HASH(start, u32, struct start_data_t);
BPF_PERF_OUTPUT(events);

// 直接回收开始
TRACEPOINT_PROBE(vmscan, mm_vmscan_direct_reclaim_begin)
{
    u32 pid = bpf_get_current_pid_tgid();
    struct start_data_t data = {};
    
    data.ts = bpf_ktime_get_ns();
    data.order = args->order;
    
    start.update(&pid, &data);
    return 0;
}

// 直接回收结束
TRACEPOINT_PROBE(vmscan, mm_vmscan_direct_reclaim_end)
{
    u32 pid = bpf_get_current_pid_tgid();
    struct start_data_t *datap;
    struct event_t event = {};
    u64 delta;
    
    datap = start.lookup(&pid);
    if (datap == 0) {
        return 0;   // 没有找到开始记录
    }
    
    delta = bpf_ktime_get_ns() - datap->ts;
    
    event.pid = pid;
    event.tgid = bpf_get_current_pid_tgid() >> 32;
    event.delta_us = delta / 1000;  // 转换为微秒
    event.order = datap->order;
    event.nr_reclaimed = args->nr_reclaimed;
    bpf_get_current_comm(&event.comm, sizeof(event.comm));
    
    events.perf_submit(args, &event, sizeof(event));
    
    start.delete(&pid);
    return 0;
}
"""

def main():
    parser = argparse.ArgumentParser(
        description="追踪直接内存回收(Direct Reclaim)操作的延迟",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    sudo python3 direct_reclaim_latency.py              # 追踪所有进程
    sudo python3 direct_reclaim_latency.py -p 1234      # 只追踪 PID 1234
    sudo python3 direct_reclaim_latency.py -m 100       # 只显示耗时 > 100us 的事件
        """)
    parser.add_argument("-p", "--pid", type=int, default=0,
                        help="只追踪指定的 PID")
    parser.add_argument("-m", "--min-latency", type=int, default=0,
                        help="只显示延迟大于此值(微秒)的事件")
    args = parser.parse_args()

    # 加载 eBPF 程序
    print("正在加载 eBPF 程序...")
    b = BPF(text=bpf_text)
    
    print("追踪 mm_vmscan_direct_reclaim 事件... Ctrl-C 退出")
    print()
    print("%-9s %-16s %-7s %-7s %-10s %-12s %-15s" % (
        "TIME", "COMM", "PID", "TGID", "ORDER", "RECLAIMED", "LATENCY(us)"))

    # 处理事件
    def print_event(cpu, data, size):
        event = b["events"].event(data)
        
        # 过滤 PID
        if args.pid and event.tgid != args.pid:
            return
        
        # 过滤最小延迟
        if event.delta_us < args.min_latency:
            return
        
        time_str = strftime("%H:%M:%S")
        print("%-9s %-16s %-7d %-7d %-10d %-12d %-15d" % (
            time_str,
            event.comm.decode('utf-8', 'replace'),
            event.pid,
            event.tgid,
            event.order,
            event.nr_reclaimed,
            event.delta_us))

    b["events"].open_perf_buffer(print_event)
    
    try:
        while True:
            b.perf_buffer_poll()
    except KeyboardInterrupt:
        print("\n退出追踪...")

if __name__ == "__main__":
    main()
