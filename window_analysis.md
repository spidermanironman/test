# 窗口焦点问题分析报告

## ANR信息
- **时间点**: 12-02 18:08:49.155 (行 5838)
- **错误类型**: `Input dispatching timed out (Application does not have a focused window).`
- **应用**: com.ss.android.ugc.aweme (抖音)
- **PID**: 26768

## 窗口状态时间线分析

### 关键时间点对比

| 时间 | 窗口 | 状态变化 | 说明 |
|------|------|----------|------|
| 18:08:48.260 | StatusBar | READY_TO_SHOW → HAS_DRAWN | 状态栏完成绘制 |
| 18:08:48.438 | NavigationBar | READY_TO_SHOW → HAS_DRAWN | 导航栏完成绘制 |
| **18:08:49.155** | **ANR发生** | **无焦点窗口** | **问题时间点** |
| 18:08:49.247 | Splash Screen | READY_TO_SHOW → HAS_DRAWN | 启动屏完成绘制（ANR后92ms） |
| 18:08:49.447 | ScreenDecorOverlayBottom | READY_TO_SHOW → HAS_DRAWN | 底部装饰层完成绘制 |
| 18:08:49.462 | ScreenDecorOverlay | DRAW_PENDING → COMMIT_DRAW_PENDING | 顶部装饰层开始绘制 |

## 问题分析

### 1. 核心问题
**应用没有获得焦点的窗口（focused window）**，导致输入事件无法分发，触发ANR。

### 2. 窗口状态异常
- ✅ **系统窗口正常**: StatusBar和NavigationBar在ANR前已完成绘制
- ⚠️ **启动屏延迟**: Splash Screen窗口在ANR发生**之后**才完成绘制（延迟92ms）
- ❌ **主窗口缺失**: **没有看到主Activity窗口的状态变化日志**

### 3. 可能的原因

#### 原因1: 主Activity窗口未及时创建
- 主Activity窗口可能在ANR发生时还未创建
- 或者窗口创建了但未及时获得焦点

#### 原因2: 窗口焦点切换失败
- Splash Screen窗口完成后，焦点应该切换到主Activity窗口
- 但主Activity窗口可能未及时响应焦点请求

#### 原因3: 窗口绘制阻塞
- 主Activity窗口可能在绘制过程中被阻塞
- 导致窗口无法及时显示并获得焦点

#### 原因4: 窗口层级问题
- 主Activity窗口可能被其他窗口遮挡
- 或者窗口层级配置错误，导致无法获得焦点

## 建议排查方向

### 1. 检查主Activity窗口日志
查找ANR时间点前后是否有主Activity窗口相关的日志：
- 窗口创建日志（Window{xxx u0 com.ss.android.ugc.aweme/...}）
- 窗口焦点变化日志（focusChanged, setFocusedApp）
- 窗口可见性变化日志（visibilityChanged）

### 2. 检查应用启动流程
- 检查Application.onCreate()是否阻塞
- 检查主Activity.onCreate()是否阻塞
- 检查是否有耗时操作在主线程执行

### 3. 检查窗口管理相关代码
- 检查Activity的窗口配置
- 检查是否有自定义WindowManager操作
- 检查是否有窗口动画或过渡效果阻塞

### 4. 检查输入事件处理
- 检查是否有输入事件在ANR前被分发但未处理
- 检查是否有输入事件队列阻塞

## 时间线详细分析

```
18:08:48.260  StatusBar完成绘制
18:08:48.438  NavigationBar完成绘制
              [约717ms间隔]
18:08:49.155  ⚠️ ANR发生 - 无焦点窗口
18:08:49.247  Splash Screen完成绘制（延迟92ms）
18:08:49.447  ScreenDecorOverlayBottom完成绘制
18:08:49.462  ScreenDecorOverlay开始绘制
```

**关键发现**: Splash Screen窗口在ANR发生后才完成绘制，说明启动屏的绘制过程可能存在问题，或者主Activity窗口的创建时机不当。

## 建议的解决方案

1. **优化启动流程**: 确保主Activity窗口在Splash Screen显示后及时创建
2. **检查主线程阻塞**: 排查是否有耗时操作阻塞了窗口创建
3. **窗口焦点管理**: 确保窗口创建后立即请求焦点
4. **添加监控**: 在窗口创建和焦点切换时添加日志，便于定位问题
