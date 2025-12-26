# Android 低内存场景模拟脚本

适用于 8GB 内存的 Android 设备，模拟低内存场景（使用约 7GB 内存，剩余约 1GB 可用）。

## 脚本说明

### 1. `android_low_memory_simulator.sh` - 完整版

功能完整的内存压力测试脚本，支持：
- 自动计算需要分配的内存量
- C 程序方式分配内存（更可靠）
- tmpfs 备用方案
- 渐进式内存压力测试
- 实时内存监控

### 2. `simple_memory_stress.sh` - 简易版

轻量级脚本，快速上手：
- 自动检测并分配内存
- 使用 tmpfs 方式（高效）
- 简单的启动/停止命令

## 使用方法

### 准备工作

1. 将脚本推送到 Android 设备：

```bash
adb push android_low_memory_simulator.sh /data/local/tmp/
adb push simple_memory_stress.sh /data/local/tmp/
```

2. 赋予执行权限：

```bash
adb shell chmod +x /data/local/tmp/android_low_memory_simulator.sh
adb shell chmod +x /data/local/tmp/simple_memory_stress.sh
```

### 简易版使用（推荐）

```bash
# 进入 adb shell（需要 root 权限以挂载 tmpfs）
adb shell
su

# 查看当前内存状态
/data/local/tmp/simple_memory_stress.sh status

# 开始低内存模拟（自动分配到剩余 1GB）
/data/local/tmp/simple_memory_stress.sh start

# 自定义分配 6GB 内存
/data/local/tmp/simple_memory_stress.sh custom 6144

# 停止并释放内存
/data/local/tmp/simple_memory_stress.sh stop
```

### 完整版使用

```bash
adb shell
su

# 查看帮助
/data/local/tmp/android_low_memory_simulator.sh help

# 查看内存状态
/data/local/tmp/android_low_memory_simulator.sh status

# 开始内存压力测试（自动计算分配量）
/data/local/tmp/android_low_memory_simulator.sh start

# 指定分配 7GB 内存
/data/local/tmp/android_low_memory_simulator.sh start 7168

# 渐进式增加内存压力（每 5 秒增加 512MB）
/data/local/tmp/android_low_memory_simulator.sh gradual 7168

# 实时监控内存状态
/data/local/tmp/android_low_memory_simulator.sh monitor

# 停止测试
/data/local/tmp/android_low_memory_simulator.sh stop
```

## 内存分配方式

脚本支持多种内存分配方式：

| 方式 | 优点 | 缺点 | 需要 Root |
|------|------|------|-----------|
| tmpfs | 稳定、高效、易于释放 | 需要挂载权限 | 是 |
| C 程序 | 精确控制、支持渐进式 | 需要编译环境 | 否 |
| 多进程 | 兼容性好 | 占用较慢 | 否 |

## 配置参数

在脚本开头可以修改以下参数：

```bash
# android_low_memory_simulator.sh
TARGET_USAGE_MB=7168        # 目标内存使用量 (7GB)
CHUNK_SIZE_MB=512           # 每个内存块大小

# simple_memory_stress.sh
TARGET_FREE_MB=1024         # 目标剩余可用内存 (1GB)
```

## 注意事项

1. **需要 Root 权限**：tmpfs 挂载方式需要 root 权限
2. **系统稳定性**：低内存状态可能导致系统卡顿或应用被杀
3. **及时释放**：测试完成后记得运行 `stop` 命令释放内存
4. **LMK 机制**：Android 的 Low Memory Killer 可能会杀死内存消耗进程

## 验证效果

运行 `status` 命令查看内存状态：

```
====== 内存状态 ======
总内存:     8192 MB
空闲内存:   512 MB
可用内存:   1024 MB
已使用:     7168 MB
======================
```

## 故障排除

1. **tmpfs 挂载失败**：确保有 root 权限
2. **内存释放不完全**：手动执行 `umount /data/local/tmp/memstress/ramfs`
3. **进程被杀**：这是正常的 LMK 行为，说明已达到低内存状态

## License

MIT License