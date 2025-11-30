# 游戏卡死问题 - 快速摘要

## 问题诊断

**症状**: 线程 sysTid=19671 被阻塞，导致游戏卡死

**根本原因**: **日志系统互斥锁竞争/死锁**

## 关键发现

### 卡死位置
```
LogdLoggerLocked (ART运行时日志锁)
  ↓
MutexLockWithTimeout (互斥锁等待)
  ↓
futex_wait (系统调用层等待)
```

### 触发路径
```
Insets状态变化处理
  → ViewRootImpl.onInsetsStateChanged
  → 日志记录调用
  → 尝试获取日志互斥锁
  → 锁被占用/死锁
  → 线程阻塞
```

## 立即行动项

1. ✅ **减少日志输出** - 特别是Insets/View更新路径上的日志
2. ✅ **检查死锁** - 查看是否有其他线程持有日志锁
3. ✅ **异步日志** - 考虑将日志操作移到后台线程
4. ✅ **性能分析** - 使用systrace/perfetto确认瓶颈

## 调试命令

```bash
# 获取所有线程堆栈
adb shell kill -3 <pid>

# Systrace分析
python systrace.py --time=10 -o trace.html sched freq idle am wm gfx view

# 检查日志输出量
adb logcat | wc -l
```

## 优先级

🔴 **高优先级** - 直接影响用户体验，需要立即处理
