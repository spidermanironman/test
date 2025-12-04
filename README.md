# Bilibili App 堆栈跟踪分析

## 概述

这是来自 **Bilibili Android 应用** (`tv.danmaku.bili`) 的原生堆栈跟踪，线程 ID 为 `sysTid=16370`。该堆栈显示了应用在 **UI 测量和布局阶段** 发生的问题（可能是 ANR 或崩溃）。

---

## 堆栈结构总览

从底部到顶部（按执行流程），堆栈可分为以下几个层次：

```
┌─────────────────────────────────────────────────────────────────┐
│  #00-#07  应用业务层 - 图片加载 & Banner 组件                      │
├─────────────────────────────────────────────────────────────────┤
│  #08-#47  Jetpack Compose 运行时 - 组合、测量、布局                │
├─────────────────────────────────────────────────────────────────┤
│  #48-#107 Compose Foundation - LazyList/Pager 布局               │
├─────────────────────────────────────────────────────────────────┤
│  #108-#137 Compose UI 节点 - 测量代理                             │
├─────────────────────────────────────────────────────────────────┤
│  #138-#191 Android View 系统 - 传统 View 测量                     │
├─────────────────────────────────────────────────────────────────┤
│  #192-#204 Android 框架 - 渲染管线 & 主循环                        │
├─────────────────────────────────────────────────────────────────┤
│  #205-#217 ART 虚拟机 & 进程启动                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 关键帧分析

### 1. 问题根源 (栈顶 #00-#07)

```
#00 kntr.base.imageloader.r0.b+208
#01 kntr.base.imageloader.ImageRequest.contentScale+56
#02 i43.a.a+224
#03 i43.a.b+504
#04 com.bilibili.ogv.kmm.operation.banner.v.z+2160
#05 com.bilibili.ogv.kmm.operation.banner.v.B+3804
#06 com.bilibili.ogv.kmm.operation.banner.v.v+552
#07 com.bilibili.ogv.kmm.operation.banner.v.c+56
```

**分析：**
- `kntr.base.imageloader` - Bilibili 的图片加载库（可能是 Konter 或类似的内部库）
- `ImageRequest.contentScale` - 正在计算图片的内容缩放
- `com.bilibili.ogv.kmm.operation.banner` - OGV（可能是"Original Generated Video"原创视频）模块的 **Banner 轮播组件**
- `kmm` 表示这是 **Kotlin Multiplatform Mobile** 代码

**问题点：** 图片加载器在 UI 测量阶段被调用来计算 `contentScale`，这可能导致主线程阻塞。

---

### 2. Jetpack Compose 运行时 (#08-#47)

```
#08 nterp_helper+2152 (ART 解释器)
#09 com.bilibili.ogv.kmm.operation.banner.p.invoke
#10-#11 androidx.compose.runtime.internal.ComposableLambdaImpl
#12-#15 BoxWithConstraintsKt (测量约束盒)
#16-#31 LayoutNodeSubcompositionsState (子组合状态)
#32-#35 BoxWithConstraints 测量
#36-#47 各种 Compose 节点测量 (AspectRatioNode, FillNode, etc.)
```

**关键组件：**
- `ComposableLambdaImpl` - Compose 可组合函数的 Lambda 实现
- `BoxWithConstraints` - 带约束的盒子布局，会触发子组合
- `LayoutNodeSubcompositionsState` - 处理子组合的状态
- `AspectRatioNode` - 宽高比节点
- `FillNode` - 填充节点

---

### 3. Compose Foundation 层 (#48-#107)

```
#48 androidx.compose.foundation.pager.PagerMeasureKt.g
#50-#54 PagerMeasurePolicyKt (Pager 测量策略)
#55-#56 LazyLayoutKt$LazyLayout
#85-#91 LazyListMeasureKt (懒加载列表测量)
```

**分析：**
- 使用了 `HorizontalPager` 或 `VerticalPager` 组件
- `LazyLayout` 是懒加载布局的基础
- `LazyList` 处理列表项的按需测量

**嵌套结构：**
```
LazyColumn/LazyRow
  └── Pager (轮播)
        └── BoxWithConstraints
              └── Banner 内容
                    └── 图片 (触发 contentScale 计算)
```

---

### 4. Compose UI 测量系统 (#108-#137)

```
#108-#114 MeasurePassDelegate (测量代理)
#115-#128 BoxMeasurePolicy, RootMeasurePolicy
#129-#137 AndroidComposeView.onMeasure
```

**关键类：**
- `MeasurePassDelegate` - 负责执行测量传递
- `SnapshotStateObserver` - 监听状态变化
- `AndroidComposeView` - Compose 与 Android View 系统的桥接

---

### 5. Android View 层级 (#138-#191)

```
#138-#141 View.measure, AbstractComposeView
#142-#145 FrameLayout, ViewPager
#147-#158 ConstraintLayout (约束布局)
#159-#172 FrameLayout, CoordinatorLayout
#173-#191 ContentFrameLayout, DecorView
```

**布局层级（从外到内）：**
```
DecorView
  └── LinearLayout
        └── FrameLayout
              └── ContentFrameLayout (AppCompat)
                    └── FrameLayout
                          └── CoordinatorLayout
                                └── FrameLayout
                                      └── ConstraintLayout
                                            └── ViewPager (androidx.viewpager)
                                                  └── FrameLayout
                                                        └── ComposeView
                                                              └── Compose UI
```

**特殊组件：**
- `PinnedBottomScrollingBehavior` - Bilibili 自定义的固定底部滚动行为
- `HeaderScrollingViewBehavior` - Material Design 的头部滚动行为

---

### 6. Android 渲染管线 (#192-#204)

```
#192-#196 ViewRootImpl.performMeasure/performTraversals/doTraversal
#197 ViewRootImpl$TraversalRunnable.run
#198-#200 Choreographer.doCallbacks/doFrame
#201-#204 Handler.dispatchMessage, Looper.loop, ActivityThread.main
```

**渲染流程：**
```
VSYNC 信号
  → Choreographer.doFrame()
    → doCallbacks()
      → TraversalRunnable.run()
        → doTraversal()
          → performTraversals()
            → measureHierarchy()
              → performMeasure()
                → View.measure() [递归测量整个 View 树]
```

---

### 7. ART 虚拟机 & 进程启动 (#205-#217)

```
#205-#209 art_quick_invoke_static_stub, Method_invoke
#210 RuntimeInit$MethodAndArgsCaller.run
#211 ZygoteInit.main
#212-#217 JNI 调用, AndroidRuntime.start, app_process64
```

这是标准的 Android 应用启动路径。

---

## 可能的问题原因

### 1. **主线程图片缩放计算**
```
kntr.base.imageloader.ImageRequest.contentScale
```
在测量阶段同步计算图片缩放可能耗时过长。

### 2. **复杂的布局嵌套**
```
LazyColumn → Pager → BoxWithConstraints → Banner → Image
```
多层懒加载 + 约束测量会触发大量计算。

### 3. **子组合开销**
`BoxWithConstraints` 会触发子组合（subcomposition），这比普通组合更昂贵。

### 4. **混合 View + Compose**
传统 View 系统（ViewPager、ConstraintLayout）与 Compose 混用增加了复杂度。

---

## 建议优化方向

1. **异步图片尺寸计算**
   - 将 `contentScale` 计算移到后台线程
   - 使用占位符避免测量时等待

2. **减少 BoxWithConstraints 使用**
   - 如果可能，使用 `Modifier.fillMaxWidth()` 等替代
   - 避免在 LazyList 项中使用

3. **简化布局层级**
   - 考虑用 Compose 的 `HorizontalPager` 替换 `ViewPager`
   - 减少不必要的 FrameLayout 嵌套

4. **延迟 Banner 加载**
   - 首屏不立即加载 Banner 图片
   - 使用 `remember` + `LaunchedEffect` 延迟初始化

---

## 技术细节

| 属性 | 值 |
|------|-----|
| 应用包名 | `tv.danmaku.bili` |
| 线程 ID | `sysTid=16370` |
| 架构 | ARM64 |
| ART 版本 | BuildId: `af9ec8284b2d47068881f2930e60d5ed` |
| 问题类型 | 可能是 ANR（UI 线程阻塞）或测量阶段崩溃 |
| 相关模块 | OGV Banner、图片加载器、Compose Pager |

---

## 文件路径说明

- `/data/app/.../base.odex` - 经过 AOT 编译的应用代码
- `/data/app/.../base.vdex` - DEX 验证文件
- `/memfd:jit-cache` - JIT 编译的代码缓存（内存文件）
- `/apex/com.android.art/lib64/libart.so` - ART 虚拟机
- `/system/framework/ocomp/arm64/boot-framework.oat` - 系统框架预编译代码
