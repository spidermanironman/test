# ANR Analysis: Input Dispatching Timeout

## ANR Summary

| Field | Value |
|-------|-------|
| **Time** | 2025-11-13 22:47:28 |
| **Application** | com.ss.android.ugc.aweme (TikTok/Douyin) |
| **Faulting Activity** | `com.ss.android.ugc.aweme/.search.activity.SearchResultActivity` |
| **Reason** | Input dispatching timed out (Application does not have a focused window) |
| **PID** | 31497 |
| **UID** | 10358 |

---

## Root Cause

**`mCurrentFocus=null`** while **`mFocusedApp=SearchResultActivity`**

The system is trying to dispatch input events to `SearchResultActivity`, but this activity has no focusable window available. The only visible window is a **Splash Screen** with `NOT_FOCUSABLE` flag set.

---

## Display #0 Focus State

```
currentFocus=null
focusedApp=ActivityRecord{233094031 u0 com.ss.android.ugc.aweme/.search.activity.SearchResultActivity t554}
```

---

## Activity Stack (Task #554)

| Position | Activity | State |
|----------|----------|-------|
| Top | `DetailActivity` | Being destroyed (`mDestroying=true`) |
| Middle | `SearchResultActivity` | **Focused App** (no window drawn) |
| Bottom | `SplashActivity` | Background |

---

## Window States

### Window #1: Splash Screen (Visible but NOT_FOCUSABLE)

| Property | Value |
|----------|-------|
| **Window** | `Window{e0ddf23 u0 Splash Screen com.ss.android.ugc.aweme}` |
| **Token** | `ActivityRecord{233094031}` (belongs to SearchResultActivity) |
| **Type** | `APPLICATION_STARTING` |
| **Flags** | `NOT_FOCUSABLE`, `NOT_TOUCHABLE`, `ALT_FOCUSABLE_IM` |
| **mHasSurface** | true |
| **isReadyForDisplay()** | true |
| **isVisible** | true |
| **mDrawState** | `HAS_DRAWN` |
| **Surface shown** | true |

**Key Issue:** This splash screen cannot receive focus due to `NOT_FOCUSABLE` flag.

---

### Window #2: DetailActivity (Being Destroyed)

| Property | Value |
|----------|-------|
| **Window** | `Window{5fd007 u0 com.ss.android.ugc.aweme/.detail.ui.DetailActivity}` |
| **Token** | `ActivityRecord{16076060}` |
| **Type** | `BASE_APPLICATION` |
| **mViewVisibility** | `0x8` (GONE) |
| **mHasSurface** | true |
| **isReadyForDisplay()** | false |
| **isVisible** | false |
| **isVisibleRequested()** | false |
| **mDrawState** | `DRAW_PENDING` |
| **mDestroying** | **true** |
| **Surface shown** | false |

**Note:** This activity holds the IME control target but is being destroyed.

---

### Window #3: SplashActivity (No Surface)

| Property | Value |
|----------|-------|
| **Window** | `Window{b3a57ba u0 com.ss.android.ugc.aweme/.splash.SplashActivity}` |
| **Token** | `ActivityRecord{103133934}` |
| **Type** | `BASE_APPLICATION` |
| **mViewVisibility** | `0x8` (GONE) |
| **mHasSurface** | false |
| **isReadyForDisplay()** | false |
| **isVisible** | false |
| **mDrawState** | `NO_SURFACE` |

---

## IME State

| Property | Value |
|----------|-------|
| **imeLayeringTarget** | `Window{5fd007}` (DetailActivity) |
| **imeInputTarget** | `Window{5fd007}` (DetailActivity) |
| **imeControlTarget** | `Window{5fd007}` (DetailActivity) |
| **mImeShowing** | false |

---

## Window Addition/Removal Timeline

```
Windows added since null focus:   [Window{e0ddf23 u0 Splash Screen com.ss.android.ugc.aweme}]
Windows removed since null focus: [Window{1ecdd89 u0 Toast}]
```

**Splash Screen added at:** 11-13 22:47:21:060

---

## Analysis

### Problem Flow:
1. User was in `DetailActivity`
2. Navigation triggered to `SearchResultActivity`
3. `DetailActivity` started being destroyed (`mDestroying=true`)
4. `SearchResultActivity` became the focused app
5. System added a Splash Screen for `SearchResultActivity` (with `NOT_FOCUSABLE` flag)
6. **`SearchResultActivity` never drew its main window**
7. Input events arrived but had no focusable window to dispatch to
8. **ANR triggered after ~5 seconds**

### Key Evidence:
- `mCurrentFocus=null` - No window can receive input
- `focusedApp=SearchResultActivity` - System expects this activity to handle input
- Splash Screen has `NOT_FOCUSABLE` flag - Cannot receive input by design
- No `BASE_APPLICATION` window for `SearchResultActivity` exists
- `DetailActivity` is `mDestroying=true` with `mDrawState=DRAW_PENDING`

---

## Conclusion

**Type:** Activity Transition ANR - No Focused Window

The ANR occurred because `SearchResultActivity` was set as the focused app but failed to draw its main window within the input dispatch timeout (typically 5 seconds). The only visible window was a non-focusable splash screen.

### Possible Causes:
1. `SearchResultActivity.onCreate()` or `onResume()` blocked on main thread
2. Heavy initialization in the activity preventing window draw
3. Network/IO operations blocking the main thread
4. Waiting for data before drawing UI
5. Activity launch was delayed/blocked

### Recommended Investigation:
1. Check main thread traces at ANR time
2. Review `SearchResultActivity` lifecycle methods for blocking operations
3. Look for synchronous network/database calls
4. Check if activity waits for Intent data before drawing
