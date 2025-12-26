#!/system/bin/sh
# ============================================================
# 简单版 Android 低内存模拟脚本
# 适用于 8GB 内存设备，快速消耗内存到低内存状态
# ============================================================

# 配置
STRESS_DIR="/data/local/tmp/memstress"
TARGET_FREE_MB=1024  # 目标剩余可用内存 (1GB)

# 创建目录
mkdir -p "$STRESS_DIR"

# 显示内存信息
show_mem() {
    echo "====== 内存状态 ======"
    free -m 2>/dev/null || cat /proc/meminfo | head -10
    echo "======================"
}

# 获取可用内存 (MB)
get_available_mb() {
    grep MemAvailable /proc/meminfo | awk '{print int($2/1024)}'
}

# 方法1: 使用 tmpfs 消耗内存 (推荐)
stress_tmpfs() {
    local size_mb=$1
    echo "[*] 使用 tmpfs 方式分配 ${size_mb}MB 内存..."
    
    local mount_point="$STRESS_DIR/ramfs"
    mkdir -p "$mount_point"
    
    # 挂载 tmpfs
    mount -t tmpfs -o size=${size_mb}m tmpfs "$mount_point" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "[!] tmpfs 挂载失败，尝试其他方法..."
        return 1
    fi
    
    # 填充数据
    echo "[*] 正在填充内存..."
    dd if=/dev/zero of="$mount_point/memfile" bs=1M count=$size_mb 2>/dev/null
    
    echo "[+] 完成! 内存已被占用"
    echo "[*] 运行 '$0 stop' 释放内存"
    return 0
}

# 方法2: 使用多个后台进程
stress_processes() {
    local total_mb=$1
    local chunk_mb=256
    local num=$((total_mb / chunk_mb))
    
    echo "[*] 启动 $num 个内存消耗进程..."
    
    for i in $(seq 1 $num); do
        # 创建一个消耗内存的后台进程
        (
            # 使用 shell 变量存储数据
            data=$(dd if=/dev/urandom bs=1M count=$chunk_mb 2>/dev/null | base64)
            echo "[+] 进程 $i: 已分配 ${chunk_mb}MB"
            # 保持进程运行
            while true; do sleep 3600; done
        ) &
        echo $! >> "$STRESS_DIR/pids.txt"
    done
    
    echo "[+] 所有进程已启动"
}

# 方法3: 使用 /dev/shm (如果可用)
stress_shm() {
    local size_mb=$1
    if [ -d "/dev/shm" ]; then
        echo "[*] 使用 /dev/shm 分配 ${size_mb}MB..."
        dd if=/dev/zero of=/dev/shm/memstress bs=1M count=$size_mb 2>/dev/null
        return 0
    fi
    return 1
}

# 停止压力测试
stop_stress() {
    echo "[*] 停止内存压力测试..."
    
    # 终止后台进程
    if [ -f "$STRESS_DIR/pids.txt" ]; then
        while read pid; do
            kill -9 $pid 2>/dev/null && echo "[+] 终止进程: $pid"
        done < "$STRESS_DIR/pids.txt"
        rm -f "$STRESS_DIR/pids.txt"
    fi
    
    # 卸载 tmpfs
    if mount | grep -q "$STRESS_DIR/ramfs"; then
        umount "$STRESS_DIR/ramfs" 2>/dev/null
        echo "[+] tmpfs 已卸载"
    fi
    
    # 清理 /dev/shm
    rm -f /dev/shm/memstress 2>/dev/null
    
    # 清理目录
    rm -rf "$STRESS_DIR/ramfs" 2>/dev/null
    
    echo "[+] 清理完成"
    show_mem
}

# 自动计算并分配
auto_stress() {
    local available=$(get_available_mb)
    local to_alloc=$((available - TARGET_FREE_MB))
    
    echo "[*] 当前可用内存: ${available}MB"
    echo "[*] 目标剩余内存: ${TARGET_FREE_MB}MB"
    echo "[*] 需要分配: ${to_alloc}MB"
    
    if [ $to_alloc -le 0 ]; then
        echo "[!] 系统已处于低内存状态"
        return 0
    fi
    
    # 优先使用 tmpfs
    if stress_tmpfs $to_alloc; then
        show_mem
        return 0
    fi
    
    # 备用方案
    stress_processes $to_alloc
    sleep 3
    show_mem
}

# 主逻辑
case "$1" in
    start)
        show_mem
        auto_stress
        ;;
    stop)
        stop_stress
        ;;
    status)
        show_mem
        if [ -f "$STRESS_DIR/pids.txt" ]; then
            echo "运行中的压力进程:"
            cat "$STRESS_DIR/pids.txt"
        fi
        ;;
    custom)
        # 自定义分配大小
        if [ -n "$2" ]; then
            show_mem
            stress_tmpfs $2 || stress_processes $2
            sleep 2
            show_mem
        else
            echo "用法: $0 custom <MB>"
        fi
        ;;
    *)
        echo "========================================"
        echo "  Android 低内存模拟脚本 (简易版)"
        echo "========================================"
        echo ""
        echo "用法: $0 <命令>"
        echo ""
        echo "命令:"
        echo "  start       - 自动分配内存到低内存状态"
        echo "  stop        - 释放所有占用的内存"
        echo "  status      - 查看当前内存状态"
        echo "  custom <MB> - 自定义分配指定大小的内存"
        echo ""
        echo "示例:"
        echo "  $0 start        # 自动填充到剩余1GB"
        echo "  $0 custom 6144  # 分配6GB内存"
        echo "  $0 stop         # 释放内存"
        echo ""
        ;;
esac
