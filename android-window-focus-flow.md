# Android 应用获得焦点窗口的流程

## 概述

在 Android 系统中，窗口焦点（Window Focus）的管理是一个涉及多个系统服务协同工作的复杂过程。当用户点击一个应用或通过其他方式切换应用时，系统需要完成一系列操作来确保正确的窗口获得焦点。

## 核心组件

### 1. WindowManagerService (WMS)
- 系统窗口管理的核心服务
- 负责所有窗口的添加、删除、布局和焦点管理
- 维护窗口的 Z-order（层级顺序）

### 2. ActivityTaskManagerService (ATMS)
- 管理 Activity 的生命周期
- 处理 Task 和 Activity 栈的管理
- 与 WMS 协调完成焦点转移

### 3. InputManagerService (IMS)
- 管理输入事件的分发
- 根据焦点窗口决定事件的目标

### 4. DisplayContent
- 代表一个显示屏幕
- 管理该屏幕上的所有窗口

## 焦点窗口获取流程

### 阶段一：触发焦点变化

焦点变化可能由以下事件触发：
1. **用户点击**：点击另一个应用的窗口
2. **Activity 启动**：新 Activity 被启动
3. **窗口关闭**：当前焦点窗口被关闭
4. **系统事件**：如来电、闹钟等

### 阶段二：WMS 焦点计算

```
WindowManagerService.updateFocusedWindowLocked()
    │
    ├── DisplayContent.updateFocusedWindowLocked()
    │       │
    │       └── findFocusedWindowIfNeeded()
    │               │
    │               └── findFocusedWindow()
    │                       │
    │                       └── 遍历窗口列表，找到符合条件的窗口
    │
    └── 通知焦点变化
```

#### findFocusedWindow() 的判断逻辑

```java
// 伪代码展示焦点窗口的选择逻辑
WindowState findFocusedWindow() {
    // 从顶层窗口开始遍历
    for (WindowState window : mWindows) {
        // 1. 检查窗口是否可以接收焦点
        if (!window.canReceiveKeys()) {
            continue;
        }
        
        // 2. 检查窗口是否可见
        if (!window.isVisible()) {
            continue;
        }
        
        // 3. 检查窗口所属的 Activity 是否可以获得焦点
        if (!window.mActivityRecord.canReceiveFocus()) {
            continue;
        }
        
        // 4. 检查是否有其他窗口阻挡
        if (isWindowBlocked(window)) {
            continue;
        }
        
        return window;
    }
    return null;
}
```

#### 窗口能否获得焦点的条件

1. **FLAG_NOT_FOCUSABLE 未设置**：窗口没有设置不可获取焦点标志
2. **窗口可见**：窗口处于可见状态
3. **Activity 状态**：所属 Activity 处于 RESUMED 或可接收焦点的状态
4. **没有被遮挡**：没有被模态对话框或其他优先级更高的窗口遮挡
5. **Display 可用**：所在的 Display 处于活动状态

### 阶段三：焦点变化通知

```
WMS.updateFocusedWindowLocked()
    │
    ├── 1. 更新 mCurrentFocus（当前焦点窗口）
    │
    ├── 2. 通知 InputManagerService
    │       │
    │       └── IMS.setFocusedWindow()
    │               │
    │               └── 更新输入事件分发目标
    │
    ├── 3. 通知旧焦点窗口
    │       │
    │       └── ViewRootImpl.windowFocusChanged(false)
    │               │
    │               └── View.onWindowFocusChanged(false)
    │
    └── 4. 通知新焦点窗口
            │
            └── ViewRootImpl.windowFocusChanged(true)
                    │
                    └── View.onWindowFocusChanged(true)
```

### 阶段四：应用侧处理

当应用窗口获得焦点时，会触发以下回调：

```java
// 1. Window.Callback.onWindowFocusChanged()
@Override
public void onWindowFocusChanged(boolean hasFocus) {
    // Activity 会收到此回调
}

// 2. View.onWindowFocusChanged()
@Override
public void onWindowFocusChanged(boolean hasWindowFocus) {
    // 视图可以在此处理焦点变化
    if (hasWindowFocus) {
        // 窗口获得焦点
        // 例如：恢复动画、刷新界面等
    } else {
        // 窗口失去焦点
        // 例如：暂停动画、保存状态等
    }
}
```

## 关键代码路径

### 1. 窗口添加时的焦点更新

```
WindowManagerService.addWindow()
    │
    ├── win = new WindowState(...)
    │
    ├── win.attach()
    │
    └── updateFocusedWindowLocked()
            │
            └── 重新计算焦点窗口
```

### 2. Activity Resume 时的焦点更新

```
ActivityRecord.onResume()
    │
    ├── 更新 Activity 状态
    │
    └── RootWindowContainer.updateFocusedWindowLocked()
            │
            └── DisplayContent.updateFocusedWindowLocked()
```

### 3. 用户触摸导致的焦点变化

```
InputDispatcher::findFocusedWindowTargetsLocked()
    │
    ├── 检查触摸点下的窗口
    │
    ├── 如果窗口可以获得焦点且不是当前焦点窗口
    │       │
    │       └── 请求 WMS 更新焦点
    │
    └── WMS.updateFocusedWindowLocked()
```

## 焦点窗口与输入事件

### 输入事件分发流程

```
InputReader (读取输入事件)
    │
    └── InputDispatcher (分发输入事件)
            │
            ├── 键盘事件 → 发送到焦点窗口
            │
            └── 触摸事件 → 发送到触摸点下的窗口
                    │
                    └── 可能触发焦点变化
```

### 焦点与键盘事件

键盘事件（包括物理键盘和软键盘）只会发送到当前拥有焦点的窗口：

```java
// InputDispatcher 中的逻辑
void InputDispatcher::dispatchKeyLocked() {
    // 获取焦点窗口
    sp<WindowInfoHandle> focusedWindow = getFocusedWindowLocked();
    
    if (focusedWindow != nullptr) {
        // 将事件发送到焦点窗口
        enqueueDispatchEntryLocked(focusedWindow, ...);
    }
}
```

## 特殊场景

### 1. 多窗口模式（分屏/自由窗口）

在多窗口模式下：
- 只有一个窗口拥有焦点
- 用户点击另一个窗口时，焦点会转移
- 非焦点窗口仍然可见，但不接收键盘事件

### 2. 对话框和 PopupWindow

```
Activity Window (失去焦点)
    │
    └── Dialog Window (获得焦点)
            │
            └── PopupWindow (可能获得焦点，取决于设置)
```

### 3. 系统窗口优先级

某些系统窗口具有更高的优先级：
- 系统对话框（TYPE_SYSTEM_DIALOG）
- 来电界面（TYPE_PHONE）
- 键盘锁（TYPE_KEYGUARD_DIALOG）

这些窗口可以抢占普通应用窗口的焦点。

### 4. IME（输入法）窗口

```
应用窗口 (保持焦点)
    │
    └── IME 窗口 (不抢占焦点)
            │
            └── 输入事件仍然发送到应用窗口
                    │
                    └── 应用窗口将事件传递给 EditText
```

输入法窗口通常设置了 `FLAG_NOT_FOCUSABLE`，不会抢占应用窗口的焦点。

## 调试焦点问题

### 使用 dumpsys 查看焦点信息

```bash
# 查看当前焦点窗口
adb shell dumpsys window | grep -E "mCurrentFocus|mFocusedApp"

# 输出示例：
# mCurrentFocus=Window{abc1234 u0 com.example.app/MainActivity}
# mFocusedApp=ActivityRecord{def5678 u0 com.example.app/.MainActivity}
```

### 查看窗口列表和状态

```bash
# 查看所有窗口
adb shell dumpsys window windows

# 查看特定应用的窗口
adb shell dumpsys window windows | grep -A 20 "com.example.app"
```

### 监控焦点变化

```bash
# 监控 WindowManager 的日志
adb logcat -s WindowManager:V

# 关注以下关键日志：
# - "Changing focus from"
# - "Focused window changed"
```

## 常见问题

### 1. 窗口无法获得焦点

可能原因：
- 设置了 `FLAG_NOT_FOCUSABLE`
- 窗口被其他窗口遮挡
- Activity 不在 RESUMED 状态
- 窗口类型不支持焦点

### 2. 焦点闪烁

可能原因：
- 窗口频繁添加/删除
- Activity 状态频繁变化
- 多个窗口竞争焦点

### 3. 键盘事件丢失

可能原因：
- 焦点窗口不是预期的窗口
- 事件被其他窗口消费
- IME 处理了事件

## 总结

Android 窗口焦点管理的核心流程：

1. **触发**：用户操作或系统事件触发焦点变化需求
2. **计算**：WMS 遍历窗口列表，找到符合条件的焦点窗口
3. **更新**：更新系统状态，通知 IMS 和相关窗口
4. **回调**：应用通过回调得知焦点变化，进行相应处理

理解这个流程对于调试窗口相关问题、优化应用体验都非常有帮助。
