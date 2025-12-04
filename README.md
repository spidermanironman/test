# 线程状态频繁切换问题诊断工具

## 问题描述
线程在RUNNABLE和RUNNING状态之间频繁交替，RUNNING状态只持续几毫秒就切换到RUNNABLE，RUNNABLE状态占用时间较长。

## 文件说明

### 1. ThreadStateDiagnosis.md
详细的问题分析和诊断方法，包括：
- Java线程状态说明
- 可能的原因分析
- 诊断方法
- 解决方案

### 2. ThreadStateMonitor.java
线程状态监控工具，可以：
- 实时监控线程状态变化
- 统计状态切换频率
- 分析各状态的持续时间
- 显示线程详细信息

**使用方法**:
```bash
javac ThreadStateMonitor.java
java ThreadStateMonitor
```

### 3. ThreadStateAnalysis.java
演示可能导致线程状态频繁切换的几种场景：
- CPU密集型任务 + 多线程竞争
- 频繁的锁竞争
- 频繁的I/O操作
- 线程数过多

**使用方法**:
```bash
javac ThreadStateAnalysis.java
java ThreadStateAnalysis
```

### 4. 解决方案建议.md
详细的优化建议和代码示例，包括：
- 快速诊断清单
- 具体解决方案
- 监控工具使用
- 性能调优参数

## 快速开始

1. 阅读 `ThreadStateDiagnosis.md` 了解问题原因
2. 运行 `ThreadStateMonitor.java` 监控你的线程
3. 运行 `ThreadStateAnalysis.java` 查看各种场景
4. 参考 `解决方案建议.md` 进行优化

## 核心要点

**重要**: Java中没有单独的RUNNING状态，RUNNABLE状态包含了：
- 正在CPU上执行（监控工具显示的RUNNING）
- 等待CPU调度（监控工具显示的RUNNABLE）

线程状态频繁切换通常是**正常现象**，只有当导致性能问题时才需要优化。