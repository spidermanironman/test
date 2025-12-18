# 音量键场景 noFocusedWindow 时间调整方案

## 1. 问题背景

### 1.1 什么是 noFocusedWindow ANR

当 InputDispatcher 分发按键事件时，如果找不到焦点窗口来接收事件，系统会等待一段时间后触发 ANR。这种 ANR 的类型就是 **noFocusedWindow**。

典型场景：
- 应用启动过程中，窗口尚未完全绘制
- Activity 切换过程中的短暂无焦点状态
- 应用主线程阻塞导致窗口无法获取焦点

### 1.2 为什么需要调整音量键的超时时间

音量键与普通触摸事件不同：
1. **用户预期不同**：按音量键时，用户期望的是音量调节，而非与当前应用交互
2. **误触可能性**：音量键更容易被意外触发
3. **对 Top 应用的特殊处理**：热门应用启动时可能需要更长的窗口准备时间

---

## 2. 核心实现原理

### 2.1 InputDispatcher 关键代码位置

```
frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
frameworks/native/services/inputflinger/dispatcher/InputDispatcher.h
```

### 2.2 默认超时时间定义

```cpp
// InputDispatcher.h
constexpr std::chrono::nanoseconds DEFAULT_INPUT_DISPATCHING_TIMEOUT = 
    std::chrono::nanoseconds(5000ms);  // 默认 5 秒

// 针对特殊场景的自定义超时
constexpr std::chrono::nanoseconds VOLUME_KEY_NOFOCUSED_TIMEOUT_FOR_TOP_APPS = 
    std::chrono::nanoseconds(10000ms); // 10 秒
```

### 2.3 关键实现函数

在 `InputDispatcher::findFocusedWindowTargetsLocked()` 中：

```cpp
InputEventInjectionResult InputDispatcher::findFocusedWindowTargetsLocked(
        nsecs_t currentTime,
        const EventEntry& entry,
        std::vector<InputTarget>& inputTargets,
        nsecs_t* nextWakeupTime) {
    
    // ...
    
    // 如果没有焦点窗口
    if (focusedWindowHandle == nullptr) {
        // 判断是否为音量键事件
        if (isVolumeKeyEvent(entry)) {
            // 获取当前前台应用
            std::string foregroundPackage = getForegroundPackageName();
            
            // 检查是否在 RUS Top 应用名单中
            if (isInTopAppList(foregroundPackage)) {
                // 使用 10 秒超时
                timeout = VOLUME_KEY_NOFOCUSED_TIMEOUT_FOR_TOP_APPS;
            } else {
                // 使用默认 5 秒超时
                timeout = DEFAULT_INPUT_DISPATCHING_TIMEOUT;
            }
        }
        
        // 检查是否超时
        if (currentTime > entry.eventTime + timeout) {
            // 触发 ANR
            onAnrLocked(/*...*/);
        }
        
        return InputEventInjectionResult::PENDING;
    }
    
    // ...
}
```

---

## 3. 详细实现步骤

### 3.1 判断是否为音量键事件

```cpp
bool InputDispatcher::isVolumeKeyEvent(const EventEntry& entry) {
    if (entry.type != EventEntry::Type::KEY) {
        return false;
    }
    
    const KeyEntry& keyEntry = static_cast<const KeyEntry&>(entry);
    int32_t keyCode = keyEntry.keyCode;
    
    return keyCode == AKEYCODE_VOLUME_UP || 
           keyCode == AKEYCODE_VOLUME_DOWN ||
           keyCode == AKEYCODE_VOLUME_MUTE;
}
```

### 3.2 RUS Top 应用名单管理

通常通过配置文件或系统属性管理：

```cpp
// 方式一：硬编码名单（不推荐，但简单）
static const std::set<std::string> TOP_APP_LIST = {
    "com.tencent.mm",          // 微信
    "com.tencent.mobileqq",    // QQ
    "com.taobao.taobao",       // 淘宝
    "com.jd.lib.jdmall",       // 京东
    "com.eg.android.AlipayGphone", // 支付宝
    // ... 更多 Top 应用
};

// 方式二：从配置文件读取（推荐）
// 配置文件位置: /system/etc/input_dispatcher_config.xml
std::set<std::string> loadTopAppList() {
    std::set<std::string> result;
    // 解析 XML 配置文件
    // ...
    return result;
}
```

### 3.3 检查应用是否在名单中

```cpp
bool InputDispatcher::isInTopAppList(const std::string& packageName) {
    // 从系统服务获取 RUS 名单
    // 或从本地缓存查询
    return mTopAppList.find(packageName) != mTopAppList.end();
}
```

### 3.4 获取前台应用包名

```cpp
std::string InputDispatcher::getForegroundPackageName() {
    // 通过 InputDispatcherPolicy 回调到 Java 层
    // 或者直接从 WindowManagerService 获取
    
    // 方式一：通过 focusedApplicationHandle
    if (mFocusedApplicationHandlesByDisplay.count(displayId) > 0) {
        auto& appHandle = mFocusedApplicationHandlesByDisplay[displayId];
        return appHandle->getName(); // 返回包名
    }
    
    // 方式二：回调到 InputDispatcherPolicy
    return mPolicy->getForegroundPackageName();
}
```

---

## 4. 系统层面集成

### 4.1 InputDispatcherPolicy 回调

Java 层需要实现相应的策略回调：

```java
// InputManagerService.java
public class InputManagerCallback implements InputManagerInternal.Callback {
    
    @Override
    public long getNoFocusedWindowTimeout(int keyCode, String packageName) {
        // 判断是否是音量键
        if (isVolumeKey(keyCode)) {
            // 检查 RUS Top 应用名单
            if (RusTopAppManager.isTopApp(packageName)) {
                return 10000; // 10 秒
            }
        }
        return 5000; // 默认 5 秒
    }
    
    private boolean isVolumeKey(int keyCode) {
        return keyCode == KeyEvent.KEYCODE_VOLUME_UP ||
               keyCode == KeyEvent.KEYCODE_VOLUME_DOWN ||
               keyCode == KeyEvent.KEYCODE_VOLUME_MUTE;
    }
}
```

### 4.2 RUS Top 应用管理服务

```java
// RusTopAppManager.java
public class RusTopAppManager {
    private static final Set<String> sTopApps = new HashSet<>();
    
    static {
        // 从配置加载
        loadFromConfig();
    }
    
    private static void loadFromConfig() {
        // 从 /system/etc/rus_top_apps.xml 加载
        // 或从服务器动态下发
    }
    
    public static boolean isTopApp(String packageName) {
        return sTopApps.contains(packageName);
    }
    
    // 支持动态更新
    public static void updateTopApps(Set<String> newList) {
        synchronized (sTopApps) {
            sTopApps.clear();
            sTopApps.addAll(newList);
        }
    }
}
```

---

## 5. 配置文件示例

### 5.1 rus_top_apps.xml

```xml
<?xml version="1.0" encoding="utf-8"?>
<rus-top-apps>
    <!-- 社交类 -->
    <app package="com.tencent.mm" timeout="10000"/>
    <app package="com.tencent.mobileqq" timeout="10000"/>
    
    <!-- 购物类 -->
    <app package="com.taobao.taobao" timeout="10000"/>
    <app package="com.jd.lib.jdmall" timeout="10000"/>
    <app package="com.xunmeng.pinduoduo" timeout="10000"/>
    
    <!-- 支付类 -->
    <app package="com.eg.android.AlipayGphone" timeout="10000"/>
    
    <!-- 视频类 -->
    <app package="com.ss.android.ugc.aweme" timeout="10000"/>
    <app package="com.tencent.qqlive" timeout="10000"/>
    
    <!-- 更多应用... -->
</rus-top-apps>
```

---

## 6. 时序流程图

```
用户按下音量键
     │
     ▼
InputReader 读取按键事件
     │
     ▼
InputDispatcher.dispatchKeyLocked()
     │
     ▼
findFocusedWindowTargetsLocked()
     │
     ├─── 有焦点窗口 ──► 正常分发事件
     │
     └─── 无焦点窗口 (noFocusedWindow)
              │
              ▼
         isVolumeKeyEvent()?
              │
              ├─── 否 ──► 使用默认 5 秒超时
              │
              └─── 是
                    │
                    ▼
              isInTopAppList()?
                    │
                    ├─── 否 ──► 使用默认 5 秒超时
                    │
                    └─── 是 ──► 使用 10 秒超时
                                   │
                                   ▼
                            等待焦点窗口
                                   │
                         ┌─────────┴─────────┐
                         │                   │
                  10秒内获得焦点        10秒后仍无焦点
                         │                   │
                         ▼                   ▼
                    正常分发事件          触发 ANR
```

---

## 7. 测试验证

### 7.1 测试命令

```bash
# 模拟音量键按下
adb shell input keyevent KEYCODE_VOLUME_UP

# 查看 InputDispatcher 日志
adb logcat -s InputDispatcher:V

# 查看 ANR 超时设置
adb shell dumpsys input | grep -i timeout
```

### 7.2 验证点

1. Top 应用启动时按音量键，确认 10 秒后才触发 ANR
2. 普通应用启动时按音量键，确认 5 秒后触发 ANR
3. 正常运行时按音量键，不应触发 ANR

---

## 8. 注意事项

1. **性能影响**：查询 Top 应用名单应该使用缓存，避免每次事件都查询
2. **名单更新**：支持动态更新 Top 应用名单，无需重启系统
3. **日志记录**：记录超时时间的变化，便于问题排查
4. **兼容性**：确保对其他按键事件不产生影响

---

## 9. 总结

通过以上实现：
- **识别音量键事件**：在 InputDispatcher 中判断 keyCode
- **查询应用名单**：检查前台应用是否在 RUS Top 名单中
- **动态调整超时**：对于 Top 应用，将 noFocusedWindow 超时从 5 秒延长到 10 秒
- **减少误报 ANR**：给予热门应用更多的窗口准备时间
