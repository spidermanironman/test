#!/system/bin/sh
# ============================================================
# Android 低内存场景模拟脚本
# 适用于 8GB 内存设备，模拟使用 7GB 内存的低内存场景
# ============================================================

# 配置参数
TARGET_USAGE_MB=7168        # 目标内存使用量 (7GB = 7168MB)
CHUNK_SIZE_MB=512           # 每个内存块大小 (512MB)
TEMP_DIR="/data/local/tmp/memstress"
PID_FILE="$TEMP_DIR/memstress.pid"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取当前内存状态
get_memory_info() {
    local mem_total=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local mem_free=$(grep MemFree /proc/meminfo | awk '{print $2}')
    local mem_available=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    local mem_buffers=$(grep Buffers /proc/meminfo | awk '{print $2}')
    local mem_cached=$(grep "^Cached:" /proc/meminfo | awk '{print $2}')
    
    echo "============================================"
    echo "           内存状态信息"
    echo "============================================"
    echo "总内存:     $((mem_total / 1024)) MB"
    echo "空闲内存:   $((mem_free / 1024)) MB"
    echo "可用内存:   $((mem_available / 1024)) MB"
    echo "Buffers:    $((mem_buffers / 1024)) MB"
    echo "Cached:     $((mem_cached / 1024)) MB"
    echo "已使用:     $(((mem_total - mem_available) / 1024)) MB"
    echo "============================================"
}

# 计算需要分配的内存量
calculate_allocation() {
    local mem_total=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local mem_available=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    local mem_total_mb=$((mem_total / 1024))
    local mem_available_mb=$((mem_available / 1024))
    local current_usage=$((mem_total_mb - mem_available_mb))
    local need_to_allocate=$((TARGET_USAGE_MB - current_usage))
    
    if [ $need_to_allocate -lt 0 ]; then
        need_to_allocate=0
    fi
    
    echo $need_to_allocate
}

# 使用 memtest 程序分配内存
# 这是一个更可靠的内存分配方式
create_memory_eater() {
    cat > "$TEMP_DIR/memeater.c" << 'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>

volatile int running = 1;

void signal_handler(int sig) {
    running = 0;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Usage: %s <size_in_mb>\n", argv[0]);
        return 1;
    }
    
    long size_mb = atol(argv[1]);
    long size_bytes = size_mb * 1024 * 1024;
    
    printf("Allocating %ld MB of memory...\n", size_mb);
    
    char *memory = (char *)malloc(size_bytes);
    if (memory == NULL) {
        printf("Failed to allocate memory!\n");
        return 1;
    }
    
    // 触碰每一页以确保内存真正被分配
    long page_size = sysconf(_SC_PAGESIZE);
    for (long i = 0; i < size_bytes; i += page_size) {
        memory[i] = (char)(i & 0xFF);
    }
    
    printf("Memory allocated and touched. PID: %d\n", getpid());
    printf("Press Ctrl+C or send SIGTERM to release memory.\n");
    
    signal(SIGTERM, signal_handler);
    signal(SIGINT, signal_handler);
    
    while (running) {
        // 定期触碰内存防止被回收
        for (long i = 0; i < size_bytes && running; i += page_size * 100) {
            memory[i] = (char)((memory[i] + 1) & 0xFF);
        }
        sleep(1);
    }
    
    printf("Releasing memory...\n");
    free(memory);
    return 0;
}
EOF
}

# 编译内存消耗程序
compile_memory_eater() {
    if [ -f "$TEMP_DIR/memeater" ]; then
        print_info "内存消耗程序已存在"
        return 0
    fi
    
    create_memory_eater
    
    # 尝试使用 ndk 或系统 gcc 编译
    if command -v gcc > /dev/null 2>&1; then
        gcc -o "$TEMP_DIR/memeater" "$TEMP_DIR/memeater.c" -O2
        if [ $? -eq 0 ]; then
            print_info "编译成功"
            return 0
        fi
    fi
    
    print_warn "无法编译 C 程序，将使用备用方法"
    return 1
}

# 备用方法：使用 dd 和 tmpfs 消耗内存
allocate_memory_tmpfs() {
    local size_mb=$1
    local file_num=$2
    local tmpfs_path="$TEMP_DIR/memfs"
    
    # 创建 tmpfs 挂载点
    if [ ! -d "$tmpfs_path" ]; then
        mkdir -p "$tmpfs_path"
        mount -t tmpfs -o size=${size_mb}m tmpfs "$tmpfs_path" 2>/dev/null
        if [ $? -ne 0 ]; then
            print_error "无法挂载 tmpfs"
            return 1
        fi
    fi
    
    # 写入数据到 tmpfs
    dd if=/dev/urandom of="$tmpfs_path/memfile_$file_num" bs=1M count=$size_mb 2>/dev/null
    print_info "已分配 ${size_mb}MB 内存 (文件 $file_num)"
}

# 使用多进程方式消耗内存
allocate_memory_multiprocess() {
    local total_mb=$1
    local num_processes=$((total_mb / CHUNK_SIZE_MB))
    local remainder=$((total_mb % CHUNK_SIZE_MB))
    
    print_info "需要分配 ${total_mb}MB 内存"
    print_info "将启动 $num_processes 个进程，每个消耗 ${CHUNK_SIZE_MB}MB"
    
    # 清理之前的进程
    stop_memory_stress
    
    mkdir -p "$TEMP_DIR"
    > "$PID_FILE"
    
    # 检查是否有编译好的程序
    if [ -f "$TEMP_DIR/memeater" ]; then
        for i in $(seq 1 $num_processes); do
            "$TEMP_DIR/memeater" $CHUNK_SIZE_MB &
            echo $! >> "$PID_FILE"
            print_info "启动进程 $i (PID: $!), 分配 ${CHUNK_SIZE_MB}MB"
            sleep 0.5
        done
        
        if [ $remainder -gt 0 ]; then
            "$TEMP_DIR/memeater" $remainder &
            echo $! >> "$PID_FILE"
            print_info "启动额外进程 (PID: $!), 分配 ${remainder}MB"
        fi
    else
        # 使用 shell 内置方式 (较慢但兼容性更好)
        for i in $(seq 1 $num_processes); do
            allocate_memory_shell $CHUNK_SIZE_MB $i &
            echo $! >> "$PID_FILE"
            print_info "启动进程 $i (PID: $!)"
            sleep 1
        done
    fi
    
    print_info "内存分配完成"
}

# Shell 方式分配内存 (兼容性方案)
allocate_memory_shell() {
    local size_mb=$1
    local id=$2
    local chunk_file="$TEMP_DIR/chunk_$id"
    
    # 使用数组在内存中保存数据
    dd if=/dev/zero bs=1M count=$size_mb 2>/dev/null | while read -r line; do
        :
    done &
    
    # 或者使用变量保存
    local data=""
    local i=0
    while [ $i -lt $((size_mb * 1024)) ]; do
        data="${data}$(head -c 1024 /dev/urandom | base64)"
        i=$((i + 1))
    done
    
    # 保持进程运行
    while true; do
        sleep 60
    done
}

# 停止内存压力测试
stop_memory_stress() {
    if [ -f "$PID_FILE" ]; then
        print_info "正在停止内存压力测试..."
        while read pid; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                kill -TERM "$pid" 2>/dev/null
                print_info "已终止进程: $pid"
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi
    
    # 卸载 tmpfs
    if mount | grep -q "$TEMP_DIR/memfs"; then
        umount "$TEMP_DIR/memfs" 2>/dev/null
        print_info "已卸载 tmpfs"
    fi
    
    # 清理临时文件
    rm -rf "$TEMP_DIR/memfs" 2>/dev/null
    
    print_info "内存压力测试已停止"
}

# 监控内存状态
monitor_memory() {
    print_info "开始监控内存状态 (按 Ctrl+C 停止)..."
    while true; do
        clear
        echo "$(date '+%Y-%m-%d %H:%M:%S')"
        get_memory_info
        
        if [ -f "$PID_FILE" ]; then
            echo ""
            echo "运行中的内存消耗进程:"
            while read pid; do
                if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                    local mem=$(ps -p $pid -o rss= 2>/dev/null)
                    if [ -n "$mem" ]; then
                        echo "  PID $pid: $((mem / 1024)) MB"
                    fi
                fi
            done < "$PID_FILE"
        fi
        
        sleep 2
    done
}

# 渐进式内存压力测试
gradual_stress() {
    local target=$1
    local step=${2:-512}
    local delay=${3:-5}
    local current=0
    
    print_info "渐进式内存压力测试"
    print_info "目标: ${target}MB, 步进: ${step}MB, 间隔: ${delay}秒"
    
    mkdir -p "$TEMP_DIR"
    > "$PID_FILE"
    
    while [ $current -lt $target ]; do
        local alloc=$step
        if [ $((current + step)) -gt $target ]; then
            alloc=$((target - current))
        fi
        
        if [ -f "$TEMP_DIR/memeater" ]; then
            "$TEMP_DIR/memeater" $alloc &
            echo $! >> "$PID_FILE"
        fi
        
        current=$((current + alloc))
        print_info "已分配: ${current}MB / ${target}MB"
        get_memory_info
        
        sleep $delay
    done
    
    print_info "渐进式压力测试完成"
}

# 显示帮助信息
show_help() {
    echo "============================================"
    echo "  Android 低内存场景模拟脚本"
    echo "============================================"
    echo ""
    echo "用法: $0 [命令] [参数]"
    echo ""
    echo "命令:"
    echo "  start [MB]     - 开始内存压力测试"
    echo "                   默认消耗到系统使用 7GB"
    echo "  stop           - 停止内存压力测试"
    echo "  status         - 显示当前内存状态"
    echo "  monitor        - 持续监控内存状态"
    echo "  gradual [MB]   - 渐进式增加内存压力"
    echo "  compile        - 编译内存消耗程序"
    echo "  help           - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start           # 使用默认值开始测试"
    echo "  $0 start 6144      # 分配 6GB 内存"
    echo "  $0 gradual 7168    # 渐进式分配到 7GB"
    echo "  $0 stop            # 停止测试"
    echo "  $0 status          # 查看内存状态"
    echo ""
}

# 主函数
main() {
    case "$1" in
        start)
            print_info "Android 低内存场景模拟器"
            get_memory_info
            
            if [ -n "$2" ]; then
                local target_mb=$2
            else
                local need_alloc=$(calculate_allocation)
                local target_mb=$need_alloc
            fi
            
            if [ $target_mb -le 0 ]; then
                print_warn "系统已处于目标内存使用状态"
                exit 0
            fi
            
            # 尝试编译
            mkdir -p "$TEMP_DIR"
            compile_memory_eater
            
            # 开始分配内存
            allocate_memory_multiprocess $target_mb
            
            echo ""
            get_memory_info
            ;;
            
        stop)
            stop_memory_stress
            get_memory_info
            ;;
            
        status)
            get_memory_info
            ;;
            
        monitor)
            monitor_memory
            ;;
            
        gradual)
            local target=${2:-$TARGET_USAGE_MB}
            mkdir -p "$TEMP_DIR"
            compile_memory_eater
            gradual_stress $target
            ;;
            
        compile)
            mkdir -p "$TEMP_DIR"
            compile_memory_eater
            ;;
            
        help|--help|-h)
            show_help
            ;;
            
        *)
            show_help
            ;;
    esac
}

# 执行主函数
main "$@"
