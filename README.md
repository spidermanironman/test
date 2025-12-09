# ANR 分析：输入事件分发超时

## ANR 概要

| 字段 | 值 |
|------|-----|
| **时间** | 2025-11-13 22:47:28 |
| **应用** | com.ss.android.ugc.aweme (抖音) |
| **出错Activity** | `com.ss.android.ugc.aweme/.search.activity.SearchResultActivity` |
| **原因** | Input dispatching timed out (Application does not have a focused window) |
| **PID** | 31497 |
| **UID** | 10358 |

---

## 根本原因

**`mCurrentFocus=null`**，但 **`mFocusedApp=SearchResultActivity`**

系统正在尝试向 `SearchResultActivity` 分发输入事件，但该 Activity 没有可获得焦点的窗口。唯一可见的窗口是一个设置了 `NOT_FOCUSABLE` 标志的 **Splash Screen（启动画面）**。

---

## Display #0 焦点状态

```
currentFocus=null
focusedApp=ActivityRecord{233094031 u0 com.ss.android.ugc.aweme/.search.activity.SearchResultActivity t554}
```

---

## Activity 栈 (Task #554)

| 位置 | Activity | 状态 |
|------|----------|------|
| 栈顶 | `DetailActivity` | 正在销毁 (`mDestroying=true`) |
| 中间 | `SearchResultActivity` | **焦点App**（窗口未绘制） |
| 栈底 | `SplashActivity` | 后台 |

---

## 窗口状态

### 窗口 #1：Splash Screen（可见但不可获得焦点）

| 属性 | 值 |
|------|-----|
| **Window** | `Window{e0ddf23 u0 Splash Screen com.ss.android.ugc.aweme}` |
| **Token** | `ActivityRecord{233094031}`（属于 SearchResultActivity） |
| **类型** | `APPLICATION_STARTING` |
| **标志** | `NOT_FOCUSABLE`, `NOT_TOUCHABLE`, `ALT_FOCUSABLE_IM` |
| **mHasSurface** | true |
| **isReadyForDisplay()** | true |
| **isVisible** | true |
| **mDrawState** | `HAS_DRAWN` |
| **Surface shown** | true |

**关键问题：** 由于设置了 `NOT_FOCUSABLE` 标志，此启动画面无法接收焦点。

---

### 窗口 #2：DetailActivity（正在销毁）

| 属性 | 值 |
|------|-----|
| **Window** | `Window{5fd007 u0 com.ss.android.ugc.aweme/.detail.ui.DetailActivity}` |
| **Token** | `ActivityRecord{16076060}` |
| **类型** | `BASE_APPLICATION` |
| **mViewVisibility** | `0x8` (GONE) |
| **mHasSurface** | true |
| **isReadyForDisplay()** | false |
| **isVisible** | false |
| **isVisibleRequested()** | false |
| **mDrawState** | `DRAW_PENDING` |
| **mDestroying** | **true** |
| **Surface shown** | false |

**注意：** 该 Activity 持有 IME 控制目标，但正在被销毁。

---

### 窗口 #3：SplashActivity（无 Surface）

| 属性 | 值 |
|------|-----|
| **Window** | `Window{b3a57ba u0 com.ss.android.ugc.aweme/.splash.SplashActivity}` |
| **Token** | `ActivityRecord{103133934}` |
| **类型** | `BASE_APPLICATION` |
| **mViewVisibility** | `0x8` (GONE) |
| **mHasSurface** | false |
| **isReadyForDisplay()** | false |
| **isVisible** | false |
| **mDrawState** | `NO_SURFACE` |

---

## IME 状态

| 属性 | 值 |
|------|-----|
| **imeLayeringTarget** | `Window{5fd007}` (DetailActivity) |
| **imeInputTarget** | `Window{5fd007}` (DetailActivity) |
| **imeControlTarget** | `Window{5fd007}` (DetailActivity) |
| **mImeShowing** | false |

---

## 窗口添加/移除时间线

```
焦点变为 null 后添加的窗口：[Window{e0ddf23 u0 Splash Screen com.ss.android.ugc.aweme}]
焦点变为 null 后移除的窗口：[Window{1ecdd89 u0 Toast}]
```

**Splash Screen 添加时间：** 11-13 22:47:21:060

---

## 分析

### 问题流程：
1. 用户在 `DetailActivity` 中
2. 触发导航跳转到 `SearchResultActivity`
3. `DetailActivity` 开始销毁 (`mDestroying=true`)
4. `SearchResultActivity` 成为焦点 App
5. 系统为 `SearchResultActivity` 添加了 Splash Screen（带有 `NOT_FOCUSABLE` 标志）
6. **`SearchResultActivity` 始终未绘制其主窗口**
7. 输入事件到达但没有可获得焦点的窗口来分发
8. **约 5 秒后触发 ANR**

### 关键证据：
- `mCurrentFocus=null` - 没有窗口可以接收输入
- `focusedApp=SearchResultActivity` - 系统期望此 Activity 处理输入
- Splash Screen 带有 `NOT_FOCUSABLE` 标志 - 设计上就无法接收输入
- `SearchResultActivity` 不存在 `BASE_APPLICATION` 类型的窗口
- `DetailActivity` 处于 `mDestroying=true` 状态，`mDrawState=DRAW_PENDING`

---

## 结论

**类型：** Activity 切换 ANR - 无焦点窗口

ANR 发生的原因是 `SearchResultActivity` 被设置为焦点 App，但未能在输入分发超时时间内（通常为 5 秒）绘制其主窗口。唯一可见的窗口是一个不可获得焦点的启动画面。

### 可能的原因：
1. `SearchResultActivity.onCreate()` 或 `onResume()` 在主线程阻塞
2. Activity 中存在大量初始化操作，阻止了窗口绘制
3. 主线程存在网络/IO 操作阻塞
4. 在绘制 UI 之前等待数据
5. Activity 启动被延迟/阻塞

### 建议排查方向：
1. 检查 ANR 发生时的主线程堆栈
2. 审查 `SearchResultActivity` 生命周期方法中的阻塞操作
3. 查找同步的网络/数据库调用
4. 检查 Activity 是否在绘制前等待 Intent 数据
