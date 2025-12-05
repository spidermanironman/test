# 广播发送全流程项目

## 文档

详细解释广播发送全流程，请查看：[广播发送全流程详解.md](./广播发送全流程详解.md)

## 内容概览

文档详细解释了从应用层调用到底层Binder通信的完整广播发送流程，包括：

1. **应用层调用** - Context.sendBroadcast()
2. **系统服务层** - ActivityManagerService处理
3. **队列管理** - BroadcastQueue调度
4. **广播分发** - 并行和有序广播处理
5. **Binder通信** - 进程间通信机制
6. **接收者处理** - BroadcastReceiver.onReceive()
7. **完成通知** - finishReceiver流程

## 关键要点

- 广播发送的完整调用链
- 并行广播 vs 有序广播的区别
- Binder IPC通信机制
- 性能优化建议
- 常见问题和解决方案