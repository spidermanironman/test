# ANR 完整分析报告：输入事件分发超时

## 一、ANR 概要信息

| 字段 | 值 |
|------|-----|
| **时间** | 2025-11-13 22:47:28.042 |
| **应用** | com.ss.android.ugc.aweme (抖音) |
| **出错 Activity** | `SearchResultActivity` |
| **ANR 类型** | Input dispatching timed out |
| **原因** | Application does not have a focused window |
| **PID** | 31497 |
| **UID** | 10358 |

---

## 二、时间线分析

```
22:47:21.046  系统下发 wm_restart_activity: SearchResultActivity
22:47:21.049  系统设置 wm_set_resumed_activity: SearchResultActivity
22:47:21.080  Splash Screen 状态变为 HAS_DRAWN（启动画面绘制完成）
22:47:24.080  ⚠️ Choreographer: Skipped 221 frames! 主线程卡顿严重
22:47:27.555  设备温度: 44.895°C（接近过热）
22:47:28.012  InputDispatcher: NoFocusedWindowAnr（无焦点窗口）
22:47:28.042  am_anr 触发 ANR
```

**关键时间差：**
- 从 Activity 启动到 ANR：**约 7 秒**
- 主线程卡顿发生时间：22:47:24（跳过 221 帧 ≈ **3.7 秒卡顿**）

---

## 三、根本原因分析

### 3.1 直接原因：无焦点窗口

```
InputDispatcher: NoFocusedWindowAnr
  FocusedWindows: <none>
  FocusRequests:
    displayId=0, name='5fd007 DetailActivity' result='NO_WINDOW'
```

**分析：**
- `mCurrentFocus=null`：当前没有焦点窗口
- `mFocusedApp=SearchResultActivity`：系统期望此 Activity 处理输入
- `DetailActivity` 请求焦点但返回 `NO_WINDOW`（窗口已销毁）
- `SearchResultActivity` 的主窗口**始终未绘制完成**

### 3.2 间接原因：主线程严重卡顿

```
Choreographer: Skipped 221 frames! The application may be doing too much work on its main thread.
```

**计算：**
- 221 帧 × 16.67ms/帧 ≈ **3.68 秒**
- 主线程在 22:47:24 前后存在严重阻塞

### 3.3 环境因素：设备高温

```
温度读取: 44.895°C
```

- 设备接近 45°C 过热阈值
- 可能触发系统降频，影响应用性能

---

## 四、窗口状态分析

### 4.1 窗口列表

| 窗口 | 所属 Activity | 可见 | 可获得焦点 | 状态 |
|------|---------------|------|------------|------|
| Splash Screen | SearchResultActivity | ✅ | ❌ (`NOT_FOCUSABLE`) | HAS_DRAWN |
| DetailActivity | DetailActivity | ❌ | - | 正在销毁 |
| SplashActivity | SplashActivity | ❌ | - | 无 Surface |

### 4.2 焦点状态

```
Display #0:
  currentFocus = null（无焦点窗口）
  focusedApp = SearchResultActivity（焦点应用）
```

**问题：** SearchResultActivity 是焦点应用，但没有可接收输入的窗口。

---

## 五、主线程堆栈分析

```
#00 syscall+32                    <- 系统调用等待
#01 ConditionVariable::Wait       <- 条件变量等待
#02-#03 CallObjectMethod          <- JNI 调用
#04 dispatchVsync                 <- Vsync 分发
#05 handleEvent                   <- 事件处理
#06 Looper::pollOnce             <- 消息循环轮询
#07 nativePollOnce               <- Native 层消息等待
#08-#10 MessageQueue.next         <- 获取下一条消息
#11-#12 Looper.loop              <- 消息循环
#13 ActivityThread.main          <- 主线程入口
```

**堆栈解读：**

| 状态 | 说明 |
|------|------|
| **当前状态** | 主线程处于空闲等待状态（`nativePollOnce`） |
| **ANR 时** | 主线程已恢复正常，正在等待新消息 |
| **问题时段** | ANR 前 3-4 秒主线程存在严重阻塞（221 帧卡顿） |

**关键发现：** ANR 抓取时主线程已空闲，但**窗口绘制在卡顿期间被延误**，导致输入分发超时。

---

## 六、问题流程还原

```
┌─────────────────────────────────────────────────────────────────┐
│  22:47:21.046  系统启动 SearchResultActivity                      │
├─────────────────────────────────────────────────────────────────┤
│  22:47:21.049  SearchResultActivity 设为 resumed 状态              │
├─────────────────────────────────────────────────────────────────┤
│  22:47:21.080  Splash Screen 绘制完成（NOT_FOCUSABLE）            │
├─────────────────────────────────────────────────────────────────┤
│  22:47:21 ~ 22:47:24                                             │
│  ⚠️ 主线程执行耗时操作                                            │
│  - 可能是 onCreate/onResume 中的初始化                            │
│  - 可能是网络/IO/数据库操作                                        │
│  - 导致窗口无法绘制                                               │
├─────────────────────────────────────────────────────────────────┤
│  22:47:24.080  Choreographer 报告跳过 221 帧（~3.7秒卡顿）         │
├─────────────────────────────────────────────────────────────────┤
│  22:47:24 ~ 22:47:28                                             │
│  - 用户触摸屏幕产生输入事件                                        │
│  - 系统尝试分发输入到 SearchResultActivity                         │
│  - 但该 Activity 没有焦点窗口                                      │
│  - DetailActivity 的焦点请求返回 NO_WINDOW                         │
├─────────────────────────────────────────────────────────────────┤
│  22:47:28.012  InputDispatcher 报告 NoFocusedWindowAnr            │
├─────────────────────────────────────────────────────────────────┤
│  22:47:28.042  系统触发 ANR                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 七、结论

### 7.1 ANR 类型
**Activity 切换场景下的无焦点窗口 ANR**

### 7.2 直接原因
`SearchResultActivity` 在成为焦点应用后，其主窗口未能在 5 秒内完成绘制并获得焦点，导致输入事件无法分发。

### 7.3 根因链路

```
主线程耗时操作（~3.7秒）
    ↓
窗口绘制被阻塞
    ↓
SearchResultActivity 无法创建焦点窗口
    ↓
只有 NOT_FOCUSABLE 的 Splash Screen 可见
    ↓
用户输入事件无处分发
    ↓
输入分发超时 → ANR
```

### 7.4 加剧因素
1. **设备高温（44.9°C）**：可能导致系统降频，性能下降
2. **SurfaceView 无帧问题**：`SurfaceView has no frame` 可能是 SurfaceFlinger 问题
3. **Activity 切换复杂**：DetailActivity 正在销毁时切换到 SearchResultActivity

---

## 八、建议排查方向

### 8.1 应用侧（抖音）
| 优先级 | 排查项 | 说明 |
|--------|--------|------|
| 🔴 高 | `SearchResultActivity.onCreate()` | 检查是否有耗时初始化 |
| 🔴 高 | `SearchResultActivity.onResume()` | 检查是否有阻塞操作 |
| 🟡 中 | 网络请求 | 是否在主线程同步等待网络数据 |
| 🟡 中 | 数据库操作 | 是否在主线程执行 DB 查询 |
| 🟢 低 | View 渲染 | 是否有复杂布局或大量 View 创建 |

### 8.2 系统侧
| 优先级 | 排查项 | 说明 |
|--------|--------|------|
| 🔴 高 | SurfaceFlinger | 排查 `SurfaceView has no frame` 问题 |
| 🟡 中 | 温控策略 | 检查 44.9°C 时是否触发降频 |
| 🟡 中 | Activity 切换 | 检查 DetailActivity 销毁与 SearchResultActivity 启动的时序 |

### 8.3 需要的额外日志
1. **ANR traces.txt**：完整的进程堆栈
2. **Systrace**：分析主线程具体在做什么（问题时间段 22:47:21-22:47:24）
3. **应用日志**：SearchResultActivity 生命周期日志
4. **SurfaceFlinger dump**：排查 `SurfaceView has no frame` 问题

---

## 九、总结

这是一个典型的 **Activity 切换过程中主线程阻塞导致的无焦点窗口 ANR**。

**核心问题：** 主线程在 `SearchResultActivity` 启动过程中存在约 3.7 秒的阻塞（跳过 221 帧），导致窗口无法及时绘制。当用户在此期间触摸屏幕时，系统找不到可以接收输入的焦点窗口，最终触发 ANR。

**责任归属：** 主要是**应用侧问题**（主线程耗时操作），但设备高温和可能的 SurfaceFlinger 问题可能是加剧因素。

**修复建议：** 
1. 将 `SearchResultActivity` 的耗时初始化移至子线程
2. 避免在生命周期方法中执行同步 IO/网络操作
3. 使用异步加载，先显示骨架屏/占位符
