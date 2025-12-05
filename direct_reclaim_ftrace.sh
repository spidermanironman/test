#!/bin/bash
# 使用 ftrace 追踪 direct reclaim 延迟的脚本
#
# 使用方法:
#   sudo ./direct_reclaim_ftrace.sh
#
# 这个脚本会启用 vmscan tracepoint 并实时显示事件

set -e

TRACEFS=/sys/kernel/debug/tracing

# 检查是否为 root
if [ "$(id -u)" -ne 0 ]; then
    echo "错误: 需要 root 权限运行此脚本"
    exit 1
fi

# 检查 tracefs 是否挂载
if [ ! -d "$TRACEFS" ]; then
    echo "错误: tracefs 未挂载于 $TRACEFS"
    echo "尝试: mount -t debugfs none /sys/kernel/debug"
    exit 1
fi

cleanup() {
    echo ""
    echo "清理追踪配置..."
    echo 0 > $TRACEFS/events/vmscan/mm_vmscan_direct_reclaim_begin/enable 2>/dev/null || true
    echo 0 > $TRACEFS/events/vmscan/mm_vmscan_direct_reclaim_end/enable 2>/dev/null || true
    echo 0 > $TRACEFS/tracing_on 2>/dev/null || true
    echo "追踪已停止"
    exit 0
}

trap cleanup INT TERM

echo "配置 ftrace 追踪 direct reclaim 事件..."

# 清空 trace buffer
echo > $TRACEFS/trace

# 启用 direct reclaim tracepoints
echo 1 > $TRACEFS/events/vmscan/mm_vmscan_direct_reclaim_begin/enable
echo 1 > $TRACEFS/events/vmscan/mm_vmscan_direct_reclaim_end/enable

# 启用追踪
echo 1 > $TRACEFS/tracing_on

echo "追踪 mm_vmscan_direct_reclaim 事件中... (Ctrl-C 停止)"
echo ""
echo "输出格式: <进程>-<PID> [CPU] <时间戳>: <事件>"
echo "---------------------------------------------------"

# 实时读取 trace_pipe
cat $TRACEFS/trace_pipe
