# 游戏卡死问题 - 快速摘要

## 问题概述
主线程阻塞在日志系统的互斥锁上，导致游戏完全卡死。

## 核心发现

### 阻塞位置
```
主线程 → InsetsSourceConsumer.applyLocalVisibilityOverride() 
      → Log.println_native() 
      → 等待日志互斥锁 (LogdLoggerLocked)
      → 阻塞在 futex_wait
```

### 根本原因
**日志系统互斥锁竞争**：主线程尝试输出日志时，日志系统的互斥锁被其他线程持有，导致主线程无限期等待。

## 立即行动项

### 🔴 高优先级
1. **移除窗口Insets处理路径中的日志输出**
   - 检查 `InsetsSourceConsumer.applyLocalVisibilityOverride()` 调用链
   - 移除或注释所有 `Log.d()`, `Log.i()`, `Log.v()` 调用

2. **检查日志输出频率**
   - 使用 `adb logcat | wc -l` 统计日志行数
   - 检查是否有日志风暴

### 🟡 中优先级
3. **收集完整诊断信息**
   - 获取完整systrace（包含所有线程）
   - 获取线程dump，找出持有日志锁的线程
   - 检查logcat输出

4. **实施日志优化**
   - 生产环境禁用DEBUG/VERBOSE日志
   - 使用日志级别控制
   - 考虑异步日志处理

## 代码检查清单

- [ ] 搜索代码中的 `Log.` 调用
- [ ] 检查 `InsetsSourceConsumer` 相关代码
- [ ] 检查 `ViewRootImpl` 相关代码
- [ ] 检查是否有自定义日志实现
- [ ] 检查日志级别配置

## 关键代码位置

根据堆栈跟踪，需要重点检查：
- `android.view.InsetsSourceConsumer.applyLocalVisibilityOverride()` 
- `android.view.InsetsController.onStateChanged()`
- `android.view.ViewRootImpl.onInsetsStateChanged()`

## 预期效果

修复后：
- ✅ 主线程不再阻塞
- ✅ 窗口Insets变化正常处理
- ✅ 游戏响应恢复正常
- ✅ 消除ANR风险
