# mm_vmscan_direct_reclaim 耗时监控

这个项目提供了几种方法来监控和记录 `mm_vmscan_direct_reclaim` 操作的耗时。

## 方法概述

### 方法1: 直接修改内核源码（需要重新编译内核）

如果你有内核源码的访问权限，可以直接在 `mm/vmscan.c` 文件中的 `mm_vmscan_direct_reclaim` 函数里添加时间戳记录。

**优点：**
- 最直接的方法
- 可以获取所有函数参数
- 性能开销最小

**缺点：**
- 需要重新编译内核
- 需要内核源码

参考 `vmscan_timing_example.c` 中的示例代码。

### 方法2: 使用内核 tracepoint（推荐）

在内核中添加 tracepoint，可以通过 ftrace/perf 等工具追踪。

**优点：**
- 不修改核心逻辑
- 可以通过标准工具追踪
- 可以动态启用/禁用

**缺点：**
- 需要修改内核源码
- 需要重新编译内核

### 方法3: 使用内核模块 + kprobes（无需修改内核源码）

使用 kprobes 技术 hook `mm_vmscan_direct_reclaim` 函数，无需修改内核源码。

**优点：**
- 无需修改内核源码
- 可以动态加载/卸载
- 不需要重新编译内核

**缺点：**
- 可能无法获取函数参数（取决于架构和调用约定）
- 对性能有轻微影响

## 使用方法（方法3：内核模块）

### 编译模块

```bash
make
```

### 加载模块

```bash
sudo make load
# 或
sudo insmod vmscan_timing_module.ko
```

### 查看日志

```bash
# 实时查看
sudo dmesg -w

# 或查看最近的日志
make logs

# 或查看系统日志
sudo tail -f /var/log/kern.log | grep mm_vmscan_direct_reclaim
```

### 卸载模块

```bash
sudo make unload
# 或
sudo rmmod vmscan_timing_module
```

## 日志格式

日志输出示例：

```
[timestamp] mm_vmscan_direct_reclaim: pid=1234 comm=myapp duration=1523456 ns (1.523 ms)
```

如果操作耗时超过 100ms，会额外打印警告：

```
[timestamp] mm_vmscan_direct_reclaim: SLOW operation detected! pid=1234 duration=125.234 ms
```

## 注意事项

1. **权限要求**：加载内核模块需要 root 权限
2. **内核版本**：确保模块与当前运行的内核版本兼容
3. **符号查找**：如果 `mm_vmscan_direct_reclaim` 不是导出的符号，kprobe 可能无法工作
4. **性能影响**：kprobes 会对性能有轻微影响，建议在调试时使用

## 如果 kprobe 无法找到符号

如果 `mm_vmscan_direct_reclaim` 不是导出的符号，可以尝试：

1. 检查符号是否存在：
   ```bash
   sudo cat /proc/kallsyms | grep mm_vmscan_direct_reclaim
   ```

2. 如果符号不存在或未导出，可能需要：
   - 修改内核源码，将函数导出（添加 `EXPORT_SYMBOL`）
   - 或者使用方法1，直接在内核源码中添加日志

## 替代方案：使用 ftrace

如果 kprobe 不可用，也可以使用 ftrace：

```bash
# 启用函数追踪
echo mm_vmscan_direct_reclaim > /sys/kernel/debug/tracing/set_ftrace_filter
echo function > /sys/kernel/debug/tracing/current_tracer
echo 1 > /sys/kernel/debug/tracing/tracing_on

# 查看追踪结果
cat /sys/kernel/debug/tracing/trace
```
