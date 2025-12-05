# Android 广播机制研究

本项目包含 Android 广播机制的相关文档和分析工具。

## 文档

- **[广播发送全流程详解.md](./广播发送全流程详解.md)** - 详细解释 Android 广播发送的完整流程，从应用层调用到系统服务处理，包括 Binder IPC 机制、线程模型、性能优化等。

## 相关资源

- [BROADCAST_BINDER.md](./BROADCAST_BINDER.md) - 广播发送与 Binder 机制说明（历史版本）

## 工具

- `check_broadcast_thread_status.py` - 检查广播处理线程状态的工具脚本