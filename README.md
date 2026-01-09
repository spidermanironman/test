# 微信 Native Crash 注入工具

用于安全测试、崩溃处理机制测试和稳定性测试的 Frida 脚本。

## 功能特性

- 多种 Crash 触发方式（空指针、abort、段错误、栈溢出等）
- Hook 微信崩溃处理器，监控崩溃处理流程
- 支持交互式控制和自动触发模式
- 详细的日志输出

## 环境要求

- Python 3.7+
- Frida 16.0+
- 已 root 的 Android 设备或模拟器
- 设备上运行 frida-server

## 安装

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 下载并安装 frida-server 到设备
# 1. 从 https://github.com/frida/frida/releases 下载对应架构的 frida-server
# 2. 推送到设备
adb push frida-server /data/local/tmp/
adb shell "chmod 755 /data/local/tmp/frida-server"

# 3. 启动 frida-server (需要 root)
adb shell "su -c '/data/local/tmp/frida-server &'"
```

## 使用方法

### 方式一：使用 Python 启动脚本

```bash
# 附加到运行中的微信
python run_crash_test.py

# 启动微信并注入
python run_crash_test.py --spawn

# 自动触发 abort crash (5秒后)
python run_crash_test.py --crash abort

# 自动触发空指针 crash (10秒后)
python run_crash_test.py --crash null_pointer --delay 10

# 列出可用设备
python run_crash_test.py --list-devices
```

### 方式二：直接使用 Frida 命令

```bash
# 附加到运行中的微信
frida -U com.tencent.mm -l wechat_native_crash.js

# 启动微信并注入
frida -U -f com.tencent.mm -l wechat_native_crash.js --no-pause
```

## 交互式命令

在 Frida 控制台中可以使用以下命令：

```javascript
// 触发各种类型的 crash
crash()                  // 使用默认方式 (null_pointer)
crash('abort')           // 触发 abort() crash
crash('null_pointer')    // 触发空指针 crash
crash('segfault')        // 触发段错误 crash
crash('stack_overflow')  // 触发栈溢出 crash
crash('divide_zero')     // 触发除零错误

// 辅助命令
help()                   // 显示帮助信息
listModules()           // 列出微信相关模块
findCrashLib()          // 查找 crash 处理库
```

## Crash 类型说明

| 类型 | 信号 | 说明 |
|------|------|------|
| `null_pointer` | SIGSEGV | 空指针解引用，最常见的崩溃类型 |
| `abort` | SIGABRT | 调用 abort() 函数 |
| `segfault` | SIGSEGV | 访问非法内存地址 |
| `stack_overflow` | SIGSEGV | 栈空间耗尽 |
| `divide_zero` | SIGFPE | 除零错误 |
| `sigkill` | SIGKILL | 强制终止信号 |
| `sigabrt` | SIGABRT | 中止信号 |
| `sigsegv` | SIGSEGV | 段错误信号 |

## 脚本配置

编辑 `wechat_native_crash.js` 中的 CONFIG 对象：

```javascript
const CONFIG = {
    triggerDelay: 5000,      // 延迟触发时间（毫秒）
    autoTrigger: false,      // 是否自动触发 crash
    crashType: 'null_pointer', // crash 类型
    verbose: true            // 是否打印详细日志
};
```

## 注意事项

1. **仅用于授权的安全测试**：请确保您有权限对目标应用进行测试
2. **设备需要 root**：Frida 需要 root 权限才能注入到其他进程
3. **备份数据**：crash 测试可能导致数据丢失，请提前备份
4. **版本兼容**：不同版本的微信可能有不同的 native 库结构

## 故障排除

### frida-server 无法启动
```bash
# 检查 SELinux 状态
adb shell getenforce

# 临时禁用 SELinux
adb shell "su -c 'setenforce 0'"
```

### 找不到微信进程
```bash
# 确认微信正在运行
adb shell "ps | grep tencent"

# 或者使用 frida 列出进程
frida-ps -U | grep -i wechat
```

### 注入失败
```bash
# 检查 frida-server 是否运行
adb shell "ps | grep frida"

# 重新启动 frida-server
adb shell "su -c 'pkill frida-server; /data/local/tmp/frida-server &'"
```

## 许可证

MIT License
