# Android堆栈跟踪分析

本仓库包含对Android应用堆栈跟踪的分析报告。

## 分析报告

- [堆栈跟踪分析报告](./stack_trace_analysis.md) - 针对"m.tencent.KiHan"进程的详细堆栈分析

## 问题概述

分析了一个Android应用的堆栈跟踪，发现线程在日志系统调用时发生阻塞，可能由日志系统死锁或过载引起。