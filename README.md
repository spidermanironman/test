# Direct Reclaim 延迟追踪工具

追踪 Linux 内核中 `mm_vmscan_direct_reclaim` 操作的耗时。当应用程序分配内存但系统内存紧张时，会触发直接内存回收（Direct Reclaim），这可能导致应用延迟。

## 背景知识

Linux 内核提供了两个相关的 tracepoint：
- `mm_vmscan_direct_reclaim_begin` - 直接回收开始
- `mm_vmscan_direct_reclaim_end` - 直接回收结束

通过计算这两个事件之间的时间差，可以得到每次直接回收操作的耗时。

## 工具说明

### 1. eBPF/BCC 脚本（推荐）

`direct_reclaim_latency.py` - 功能最完整，支持过滤和详细输出。

**安装依赖：**
```bash
# Ubuntu/Debian
sudo apt-get install bpfcc-tools python3-bpfcc

# CentOS/RHEL
sudo yum install bcc-tools python3-bcc
```

**使用方法：**
```bash
# 追踪所有进程
sudo python3 direct_reclaim_latency.py

# 只追踪指定 PID
sudo python3 direct_reclaim_latency.py -p 1234

# 只显示延迟 > 100 微秒的事件
sudo python3 direct_reclaim_latency.py -m 100
```

**输出示例：**
```
TIME      COMM             PID     TGID    ORDER      RECLAIMED    LATENCY(us)
14:23:45  java             12345   12345   0          32           1523
14:23:46  python3          5678    5678    2          128          4521
```

### 2. bpftrace 脚本（简洁版）

`direct_reclaim_latency.bt` - 简洁的 bpftrace 脚本，带延迟直方图。

**安装依赖：**
```bash
# Ubuntu/Debian
sudo apt-get install bpftrace

# CentOS/RHEL
sudo yum install bpftrace
```

**使用方法：**
```bash
sudo bpftrace direct_reclaim_latency.bt
```

**输出示例：**
```
追踪 direct reclaim 延迟... Ctrl-C 退出
TIME                 COMM             PID     ORDER      LATENCY(us)
2024-01-15 14:23:45  java             12345   0          1523
2024-01-15 14:23:46  python3          5678    2          4521

--- Direct Reclaim 延迟分布 (微秒) ---
@latency_us:
[256, 512)             5 |@@@@@@@@@@                              |
[512, 1K)             12 |@@@@@@@@@@@@@@@@@@@@@@@@                |
[1K, 2K)              20 |@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@|
[2K, 4K)               8 |@@@@@@@@@@@@@@@@                        |
```

### 3. ftrace 脚本（无需安装额外工具）

`direct_reclaim_ftrace.sh` - 使用内核内置的 ftrace，无需安装任何工具。

**使用方法：**
```bash
chmod +x direct_reclaim_ftrace.sh
sudo ./direct_reclaim_ftrace.sh
```

**输出示例：**
```
追踪 mm_vmscan_direct_reclaim 事件中... (Ctrl-C 停止)

java-12345  [003]  123.456789: mm_vmscan_direct_reclaim_begin: order=0
java-12345  [003]  123.458312: mm_vmscan_direct_reclaim_end: nr_reclaimed=32
```

注意：ftrace 方式需要手动计算时间差（通过时间戳相减）。

## 输出字段说明

| 字段 | 说明 |
|------|------|
| TIME | 事件发生时间 |
| COMM | 进程名称 |
| PID | 进程 ID |
| TGID | 线程组 ID（主进程 ID）|
| ORDER | 内存分配 order（2^order 个页面）|
| RECLAIMED | 成功回收的页面数 |
| LATENCY | 操作耗时（微秒）|

## 性能影响

这些追踪工具的性能开销很小：
- eBPF 和 bpftrace：开销极低，适合生产环境
- ftrace：开销较低，但持续写入 trace buffer 可能有一定影响

## 故障排查

如果遇到权限问题：
```bash
# 确保以 root 运行
sudo su

# 或者使用 CAP_BPF 和 CAP_PERFMON 权限
sudo setcap cap_bpf,cap_perfmon+ep /usr/bin/bpftrace
```

如果 tracepoint 不存在：
```bash
# 检查可用的 vmscan tracepoints
sudo ls /sys/kernel/debug/tracing/events/vmscan/
```
