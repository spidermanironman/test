# 渲染加载动画时主线程卡顿原因分析

## 概述

当页面显示加载动画（如 spinner、进度条、骨架屏）时，如果主线程被耗时任务阻塞，动画就会出现卡顿、冻结的现象。这是因为浏览器的渲染和 JavaScript 执行共享同一个主线程。

## 主线程的工作内容

浏览器主线程需要处理以下任务：

```
┌─────────────────────────────────────────────────────────────┐
│                       主线程 (Main Thread)                    │
├─────────────────────────────────────────────────────────────┤
│  JavaScript 执行  │  样式计算  │  布局  │  绑定  │  合成  │
│     (JS Parse)    │  (Style)   │(Layout)│(Paint) │(Composite)│
└─────────────────────────────────────────────────────────────┘
```

为了保持 60fps 的流畅动画，每帧只有约 **16.67ms** 的时间预算。

## 导致卡顿的主要原因

### 1. 🔴 长时间 JavaScript 执行

**最常见的卡顿原因**

```javascript
// ❌ 会阻塞主线程的操作
function processLargeData() {
  const data = fetchSyncData(); // 同步请求
  for (let i = 0; i < 1000000; i++) {
    // 大量计算
    heavyComputation(data[i]);
  }
  return result;
}

// ✅ 改进方案：分片处理
async function processLargeDataAsync() {
  const data = await fetchData();
  const chunkSize = 1000;
  
  for (let i = 0; i < data.length; i += chunkSize) {
    const chunk = data.slice(i, i + chunkSize);
    processChunk(chunk);
    
    // 让出主线程，让动画有机会渲染
    await new Promise(resolve => setTimeout(resolve, 0));
    // 或使用 requestIdleCallback
  }
}
```

**常见耗时 JS 操作：**
| 操作类型 | 耗时程度 | 示例 |
|---------|---------|------|
| 同步 XHR 请求 | 🔴 极高 | `XMLHttpRequest` 同步模式 |
| 大数据解析 | 🔴 高 | `JSON.parse()` 大文件 |
| 复杂正则匹配 | 🟠 中高 | 对长字符串执行复杂正则 |
| 大数组操作 | 🟠 中 | `sort()`, `filter()`, `map()` 大数组 |
| 深度递归 | 🟠 中 | 树遍历、深拷贝 |
| 加密/解密 | 🔴 高 | 同步加密大数据 |

---

### 2. 🔴 强制同步布局 (Forced Synchronous Layout)

**又称"布局抖动"(Layout Thrashing)**

```javascript
// ❌ 触发强制同步布局
function badLayout() {
  for (let i = 0; i < elements.length; i++) {
    // 读取布局属性会强制浏览器立即计算布局
    const height = elements[i].offsetHeight;  // 读
    elements[i].style.height = height + 10 + 'px';  // 写
    // 每次循环都会触发一次完整的布局计算！
  }
}

// ✅ 批量读取，批量写入
function goodLayout() {
  // 先批量读取
  const heights = elements.map(el => el.offsetHeight);
  
  // 再批量写入
  elements.forEach((el, i) => {
    el.style.height = heights[i] + 10 + 'px';
  });
}
```

**触发强制布局的属性：**
```javascript
// 以下属性读取会触发强制布局
element.offsetTop / offsetLeft / offsetWidth / offsetHeight
element.clientTop / clientLeft / clientWidth / clientHeight
element.scrollTop / scrollLeft / scrollWidth / scrollHeight
element.getBoundingClientRect()
element.getComputedStyle()
element.innerText  // 需要布局信息来确定文本
```

---

### 3. 🟠 大量 DOM 操作

```javascript
// ❌ 频繁操作 DOM
function badDOMOperation() {
  for (let i = 0; i < 1000; i++) {
    const div = document.createElement('div');
    div.textContent = `Item ${i}`;
    container.appendChild(div);  // 每次都触发重排
  }
}

// ✅ 使用 DocumentFragment
function goodDOMOperation() {
  const fragment = document.createDocumentFragment();
  
  for (let i = 0; i < 1000; i++) {
    const div = document.createElement('div');
    div.textContent = `Item ${i}`;
    fragment.appendChild(div);
  }
  
  container.appendChild(fragment);  // 只触发一次重排
}

// ✅ 或使用虚拟 DOM / innerHTML
function betterDOMOperation() {
  const html = Array.from({ length: 1000 }, (_, i) => 
    `<div>Item ${i}</div>`
  ).join('');
  
  container.innerHTML = html;
}
```

---

### 4. 🟠 复杂的 CSS 样式计算

```css
/* ❌ 复杂选择器 - 计算成本高 */
.container > div:nth-child(odd) .item:not(.disabled):hover span::before {
  /* 浏览器需要大量计算来匹配 */
}

/* ✅ 简单直接的类选择器 */
.item-highlight {
  /* 更快的样式匹配 */
}
```

**耗性能的 CSS 属性：**
```css
/* 🔴 触发布局 (Layout) 的属性 */
width, height, padding, margin, border
top, left, right, bottom, position
display, float, overflow
font-size, line-height, text-align

/* 🟠 只触发绘制 (Paint) 的属性 */
color, background, box-shadow
border-radius, outline

/* 🟢 只触发合成 (Composite) - 性能最好 */
transform, opacity
```

---

### 5. 🟠 大量事件监听器

```javascript
// ❌ 每个元素都绑定事件
items.forEach(item => {
  item.addEventListener('click', handleClick);
  item.addEventListener('mouseover', handleHover);
});

// ✅ 事件委托
container.addEventListener('click', (e) => {
  if (e.target.matches('.item')) {
    handleClick(e);
  }
});
```

---

### 6. 🔴 同步资源加载

```javascript
// ❌ 同步加载脚本会阻塞渲染
<script src="heavy-library.js"></script>

// ✅ 异步加载
<script src="heavy-library.js" async></script>
<script src="heavy-library.js" defer></script>

// ✅ 动态导入
const module = await import('./heavy-module.js');
```

---

## 如何诊断主线程卡顿

### 1. Chrome DevTools Performance 面板

```
打开方式: F12 → Performance → Record
```

关注以下指标：
- **Long Tasks** (红色标记): 超过 50ms 的任务
- **Main Thread Activity**: 查看主线程在做什么
- **Frame Rate**: 帧率下降的位置

### 2. 性能监控 API

```javascript
// 监控长任务
const observer = new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    console.log('Long Task detected:', {
      duration: entry.duration,
      startTime: entry.startTime,
      name: entry.name
    });
  }
});

observer.observe({ entryTypes: ['longtask'] });
```

### 3. 帧率监控

```javascript
let lastTime = performance.now();
let frameCount = 0;

function checkFPS() {
  frameCount++;
  const now = performance.now();
  
  if (now - lastTime >= 1000) {
    console.log(`FPS: ${frameCount}`);
    frameCount = 0;
    lastTime = now;
  }
  
  requestAnimationFrame(checkFPS);
}

checkFPS();
```

---

## 解决方案总结

### 1. 使用 Web Workers

```javascript
// main.js
const worker = new Worker('worker.js');

worker.postMessage({ data: largeData });

worker.onmessage = (e) => {
  console.log('处理完成:', e.data);
};

// worker.js
self.onmessage = (e) => {
  const result = heavyComputation(e.data);
  self.postMessage(result);
};
```

### 2. 任务分片 (Task Scheduling)

```javascript
// 使用 scheduler API (现代浏览器)
async function processWithScheduler() {
  for (const item of items) {
    await scheduler.postTask(() => processItem(item), {
      priority: 'background'
    });
  }
}

// 或使用 requestIdleCallback
function processWhenIdle(items) {
  let index = 0;
  
  function processNext(deadline) {
    while (index < items.length && deadline.timeRemaining() > 0) {
      processItem(items[index++]);
    }
    
    if (index < items.length) {
      requestIdleCallback(processNext);
    }
  }
  
  requestIdleCallback(processNext);
}
```

### 3. 使用 CSS 动画替代 JS 动画

```css
/* ✅ CSS 动画使用 GPU 加速，不阻塞主线程 */
.loading-spinner {
  animation: spin 1s linear infinite;
  will-change: transform;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

### 4. 虚拟滚动

对于大列表，使用虚拟滚动只渲染可见区域：

```javascript
// 使用库如 react-virtualized, vue-virtual-scroller
// 或实现简单的虚拟滚动
function virtualScroll(container, items, itemHeight) {
  const visibleCount = Math.ceil(container.clientHeight / itemHeight);
  const startIndex = Math.floor(container.scrollTop / itemHeight);
  
  // 只渲染可见的项目
  renderItems(items.slice(startIndex, startIndex + visibleCount + 1));
}
```

---

## 最佳实践清单

- [ ] 避免同步 XHR 请求，使用 `fetch` + `async/await`
- [ ] 大数据处理使用 Web Workers
- [ ] 长任务分片处理，使用 `requestIdleCallback` 或 `setTimeout`
- [ ] 批量 DOM 操作，使用 `DocumentFragment`
- [ ] 避免强制同步布局，分离读写操作
- [ ] 使用 CSS `transform` 和 `opacity` 做动画
- [ ] 大列表使用虚拟滚动
- [ ] 使用 `defer` 或 `async` 加载脚本
- [ ] 定期使用 Performance 面板检查性能

---

## 参考资源

- [Chrome DevTools Performance](https://developer.chrome.com/docs/devtools/performance/)
- [Rendering Performance](https://web.dev/rendering-performance/)
- [Avoid Large, Complex Layouts](https://web.dev/avoid-large-complex-layouts-and-layout-thrashing/)
- [Optimize JavaScript Execution](https://web.dev/optimize-javascript-execution/)
