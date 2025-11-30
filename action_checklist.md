# 游戏卡死问题 - 快速行动清单

## 🔴 紧急处理（立即执行）

- [ ] **定位日志调用位置**
  - 搜索代码库中的 `applyLocalVisibilityOverride` 方法
  - 查找该方法及其调用链中的所有 `Log.d()`, `Log.i()`, `Log.v()` 等调用
  - 特别关注 `InsetsSourceConsumer` 和 `InsetsController` 相关类

- [ ] **临时移除日志调用**
  - 注释掉或移除上述位置的所有日志调用
  - 重新编译并测试，验证卡死问题是否消失

- [ ] **检查其他线程的日志调用**
  - 使用 Android Studio Profiler 或 systrace 查找持有日志锁的线程
  - 检查该线程在持有锁期间执行的操作

## 🟡 短期修复（1-2天内）

- [ ] **代码审查**
  - 审查所有 UI 更新路径（特别是高频调用的方法）
  - 确保没有同步日志调用
  - 建立代码审查规则，禁止在主线程 UI 路径中使用同步日志

- [ ] **实现异步日志**
  - 如果确实需要日志，实现异步日志机制
  - 使用 Handler + HandlerThread 或线程池

- [ ] **添加性能监控**
  - 在关键路径添加耗时监控
  - 设置告警阈值（如超过 16ms 记录警告）

## 🟢 长期优化（1周内）

- [ ] **建立日志策略**
  - 生产环境关闭 DEBUG/VERBOSE 日志
  - 使用 BuildConfig 控制日志级别
  - 考虑使用远程日志服务

- [ ] **优化 Insets 处理**
  - 减少 `onInsetsStateChanged()` 中的处理逻辑
  - 考虑延迟或批量处理插入状态变化

- [ ] **建立监控机制**
  - 定期运行 systrace 分析
  - 监控主线程阻塞情况
  - 建立性能回归测试

## 📋 代码搜索命令

### 查找可疑日志调用
```bash
# 搜索 InsetsSourceConsumer 相关代码
grep -r "applyLocalVisibilityOverride" --include="*.java" --include="*.kt"

# 搜索 InsetsController 中的日志调用
grep -r "InsetsController" --include="*.java" --include="*.kt" -A 10 | grep -i "log\."

# 搜索所有日志调用（用于统计）
grep -r "Log\." --include="*.java" --include="*.kt" | wc -l
```

### 查找持有日志锁的线程（需要 systrace）
```bash
# 如果 systrace 是文本格式
grep -i "futex\|mutex" systrace.txt

# 查找主线程的阻塞事件
grep -i "main\|KiHan" systrace.txt | grep -i "futex_wait"
```

## 🔍 Systrace 分析检查项

如果提供了 systrace 文件，检查以下内容：

- [ ] **主线程状态**
  - 主线程在问题时间点的状态（应该是 `D` - Uninterruptible Sleep）
  - 阻塞持续时间

- [ ] **持有日志锁的线程**
  - 哪个线程持有 `futex`/`mutex` 锁？
  - 持有锁的时长
  - 该线程在持有锁期间执行的操作

- [ ] **锁竞争情况**
  - 有多少线程在等待日志锁？
  - 等待时间分布
  - 是否存在死锁模式

- [ ] **相关事件频率**
  - `insets_control_changed` 事件的调用频率
  - 是否与日志调用重叠

## 📊 验证步骤

1. **修复前**
   - [ ] 记录问题复现步骤
   - [ ] 使用 systrace 捕获问题发生时的数据
   - [ ] 记录主线程阻塞时长

2. **修复后**
   - [ ] 使用相同步骤复现，确认问题消失
   - [ ] 使用 systrace 确认主线程不再阻塞
   - [ ] 性能测试，确保没有引入新的问题

3. **回归测试**
   - [ ] 测试窗口插入状态变化场景（旋转屏幕、键盘显示/隐藏等）
   - [ ] 测试其他可能触发日志调用的场景
   - [ ] 长时间运行测试，确保稳定性

## 📝 问题记录模板

```
问题描述: 游戏在主线程处理窗口插入状态变化时卡死

堆栈信息:
- 线程: sysTid=19671 (主线程)
- 阻塞位置: LogdLoggerLocked::operator() -> mutex::lock()
- 调用链: InsetsController.onStateChanged() -> applyLocalVisibilityOverride() -> Log.println_native()

根本原因: [填写分析结果]
修复方案: [填写修复措施]
验证结果: [填写测试结果]
```

## 🛠️ 工具推荐

- **Android Studio Profiler**: 监控线程状态和锁竞争
- **Systrace**: 系统级性能分析
- **StrictMode**: 检测主线程中的耗时操作
- **BlockCanary**: 检测主线程阻塞

## ⚠️ 注意事项

1. **不要在生产环境启用详细日志**
   - 使用 `BuildConfig.DEBUG` 控制日志
   - 生产环境只保留 ERROR 级别日志

2. **避免在 UI 线程中使用同步 I/O**
   - 日志写入是同步 I/O 操作
   - 应该使用异步方式

3. **定期检查性能**
   - 使用工具定期分析应用性能
   - 及时发现潜在问题
