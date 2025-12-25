# HWASan (Hardware-assisted AddressSanitizer) 详解

## 目录

1. [概述](#概述)
2. [工作原理](#工作原理)
3. [与 ASan 的区别](#与-asan-的区别)
4. [支持的平台](#支持的平台)
5. [基本用法](#基本用法)
6. [编译选项](#编译选项)
7. [运行时选项](#运行时选项)
8. [检测的错误类型](#检测的错误类型)
9. [代码示例](#代码示例)
10. [Android 上的使用](#android-上的使用)
11. [最佳实践](#最佳实践)
12. [常见问题](#常见问题)

---

## 概述

**HWASan (Hardware-assisted AddressSanitizer)** 是一种基于硬件的内存错误检测工具，由 Google 开发并集成在 LLVM/Clang 编译器中。它是传统 AddressSanitizer (ASan) 的改进版本，利用 ARM64 架构的 **Top Byte Ignore (TBI)** 特性来实现更高效的内存标记。

### 主要特点

- **低内存开销**：相比 ASan 的 ~2x 内存开销，HWASan 仅有约 **6-15%** 的额外内存消耗
- **硬件加速**：利用 ARM64 的 TBI 特性，无需影子内存的复杂查找
- **随机标记**：使用随机 tag 值，可检测更多类型的内存错误
- **生产环境友好**：由于开销较低，可在生产环境中启用

---

## 工作原理

### 核心机制：Top Byte Ignore (TBI)

在 ARM64 架构上，虚拟地址只使用低 48 位（或 52 位），高 16 位被忽略。HWASan 利用指针的**最高 8 位**来存储内存标记 (tag)：

```
64-bit 指针结构:
┌────────┬──────────────────────────────────────────────────────┐
│  Tag   │                    实际地址                          │
│ (8 bit)│                   (56 bit)                          │
└────────┴──────────────────────────────────────────────────────┘
```

### 标记与验证流程

1. **内存分配时**：为分配的内存块分配一个随机的 8 位 tag
2. **指针标记**：将 tag 嵌入返回的指针的高 8 位
3. **内存标记**：将相同的 tag 存储在影子内存中（每 16 字节对应 1 字节 tag）
4. **内存访问时**：比较指针中的 tag 和影子内存中的 tag
5. **不匹配时**：报告内存错误

```
内存布局示例:

实际内存:
┌─────────────────┬─────────────────┬─────────────────┐
│   16 bytes      │   16 bytes      │   16 bytes      │
│   (tag=0x1A)    │   (tag=0x1A)    │   (tag=0x2B)    │
└─────────────────┴─────────────────┴─────────────────┘

影子内存:
┌──────┬──────┬──────┐
│ 0x1A │ 0x1A │ 0x2B │
└──────┴──────┴──────┘
```

---

## 与 ASan 的区别

| 特性 | ASan | HWASan |
|------|------|--------|
| **内存开销** | ~2x-3x | ~6-15% |
| **CPU 开销** | ~2x | ~2x |
| **影子内存比例** | 1:8 | 1:16 |
| **检测精度** | 精确 | 概率性（1/256） |
| **栈内存检测** | 有限 | 更好 |
| **UAF 检测** | 需要隔离区 | 随机检测 |
| **支持平台** | 多平台 | 主要 ARM64 |
| **生产环境** | 不推荐 | 可以使用 |

### 为什么 HWASan 更适合生产环境？

1. **更低的内存开销**使其可在内存受限的设备上运行
2. **无需大型隔离区**来检测 use-after-free
3. **对实际应用的性能影响更小**

---

## 支持的平台

### 完全支持
- **ARM64/AArch64 Linux**
- **Android (ARM64)** - 从 Android 10 开始原生支持
- **ARM64 Fuchsia**

### 实验性支持
- **x86_64 Linux** - 使用 Intel LAM (Linear Address Masking) 或软件模拟
- **RISC-V** - 开发中

### 系统要求
- **编译器**：Clang 7.0+ (推荐使用最新版本)
- **内核**：Linux 4.14+ (需要 TBI 支持)
- **C 库**：glibc 2.27+ 或 musl

---

## 基本用法

### 编译启用 HWASan

```bash
# 基本编译
clang++ -fsanitize=hwaddress -g -o program program.cpp

# 推荐的完整编译选项
clang++ -fsanitize=hwaddress \
        -fno-omit-frame-pointer \
        -g \
        -O1 \
        -o program program.cpp
```

### 链接选项

```bash
# 静态链接运行时库
clang++ -fsanitize=hwaddress -static-libsan -o program program.cpp

# 共享库
clang++ -fsanitize=hwaddress -shared-libsan -o program program.cpp
```

### 运行程序

```bash
# 直接运行
./program

# 带运行时选项
HWASAN_OPTIONS="verbosity=1:halt_on_error=0" ./program
```

---

## 编译选项

### 核心选项

| 选项 | 说明 |
|------|------|
| `-fsanitize=hwaddress` | 启用 HWASan |
| `-g` | 生成调试信息（强烈推荐） |
| `-fno-omit-frame-pointer` | 保留栈帧指针，改善错误报告 |
| `-O1` 或 `-O2` | 优化级别（-O0 可能导致过多检测） |

### 高级选项

```bash
# 仅检测特定类型的操作
-fsanitize=hwaddress -mllvm -hwasan-instrument-reads=0    # 不检测读操作
-fsanitize=hwaddress -mllvm -hwasan-instrument-writes=0   # 不检测写操作
-fsanitize=hwaddress -mllvm -hwasan-instrument-atomics=0  # 不检测原子操作

# 栈检测选项
-fsanitize=hwaddress -mllvm -hwasan-instrument-stack=1    # 启用栈检测（默认）
-fsanitize=hwaddress -mllvm -hwasan-instrument-stack=0    # 禁用栈检测

# 全局变量检测
-fsanitize=hwaddress -mllvm -hwasan-globals=1             # 启用全局变量检测

# 自定义 tag 粒度
-fsanitize=hwaddress -mllvm -hwasan-memory-access-callback-prefix=__custom_hwasan
```

### 与其他选项配合

```bash
# 结合 LTO 使用
clang++ -fsanitize=hwaddress -flto -o program program.cpp

# 结合 UBSan 使用
clang++ -fsanitize=hwaddress,undefined -o program program.cpp

# 生成覆盖率信息
clang++ -fsanitize=hwaddress -fprofile-instr-generate -fcoverage-mapping -o program program.cpp
```

---

## 运行时选项

通过 `HWASAN_OPTIONS` 环境变量配置：

```bash
export HWASAN_OPTIONS="option1=value1:option2=value2"
```

### 常用选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `halt_on_error` | 1 | 发现错误时是否停止执行 |
| `verbosity` | 0 | 输出详细程度 (0-2) |
| `print_stats` | 0 | 退出时打印统计信息 |
| `print_stats_on_exit` | 0 | 退出时打印详细统计 |
| `allocator_may_return_null` | 0 | 分配失败时返回 NULL 而非终止 |
| `symbolize` | 1 | 符号化堆栈跟踪 |
| `external_symbolizer_path` | - | 指定 symbolizer 路径 |
| `log_path` | stderr | 日志输出路径 |
| `disable_coredump` | 0 | 禁用核心转储 |
| `malloc_context_size` | 30 | 分配时保存的调用栈深度 |
| `free_checks_tail_magic` | 1 | 检查释放时的尾部魔数 |
| `max_malloc_fill_size` | 0 | 新分配内存的填充大小 |
| `malloc_fill_byte` | 0xbe | 填充字节值 |
| `suppressions` | - | 抑制规则文件路径 |

### 使用示例

```bash
# 不在第一个错误时停止，收集所有错误
HWASAN_OPTIONS="halt_on_error=0" ./program

# 详细输出模式
HWASAN_OPTIONS="verbosity=2:print_stats=1" ./program

# 将输出写入文件
HWASAN_OPTIONS="log_path=/tmp/hwasan_log" ./program

# 使用抑制规则
HWASAN_OPTIONS="suppressions=/path/to/suppressions.txt" ./program
```

### 抑制规则示例

创建 `suppressions.txt` 文件：

```
# 抑制特定函数中的错误
interceptor_via_fun:function_name

# 抑制特定库中的错误
interceptor_via_lib:libfoo.so

# 抑制特定类型的错误
tag-mismatch:source_file.cpp
```

---

## 检测的错误类型

### 1. 堆缓冲区溢出 (Heap Buffer Overflow)

```cpp
// 示例：堆缓冲区溢出
int *arr = new int[10];
arr[10] = 42;  // 错误：越界访问
delete[] arr;
```

**错误报告示例：**

```
==ERROR: HWAddressSanitizer: tag-mismatch on address 0x0a1b2c3d4e5f
WRITE of size 4 at 0x0a1b2c3d4e5f tags: 1a/00 (ptr/mem)
    #0 0x55... in main test.cpp:3
    ...
Cause: heap-buffer-overflow
0x0a1b2c3d4e5f is located 0 bytes after 40-byte region [0x..., 0x...)
allocated by thread T0 here:
    #0 0x... in operator new[](unsigned long)
    #1 0x... in main test.cpp:2
```

### 2. 栈缓冲区溢出 (Stack Buffer Overflow)

```cpp
// 示例：栈缓冲区溢出
void foo() {
    char buffer[10];
    buffer[20] = 'x';  // 错误：栈溢出
}
```

### 3. 释放后使用 (Use After Free)

```cpp
// 示例：释放后使用
int *ptr = new int(42);
delete ptr;
int value = *ptr;  // 错误：使用已释放的内存
```

**错误报告示例：**

```
==ERROR: HWAddressSanitizer: tag-mismatch on address 0x0a1b2c3d4e5f
READ of size 4 at 0x0a1b2c3d4e5f tags: 1a/2b (ptr/mem)
    #0 0x55... in main test.cpp:4
    ...
Cause: use-after-free
0x0a1b2c3d4e5f was freed by thread T0 here:
    #0 0x... in operator delete(void*)
    #1 0x... in main test.cpp:3
previously allocated by thread T0 here:
    #0 0x... in operator new(unsigned long)
    #1 0x... in main test.cpp:2
```

### 4. 返回后使用栈内存 (Use After Return)

```cpp
// 示例：返回后使用栈内存
int* foo() {
    int local = 42;
    return &local;  // 危险：返回局部变量地址
}

void bar() {
    int* ptr = foo();
    *ptr = 100;  // 错误：使用已无效的栈内存
}
```

### 5. 作用域后使用 (Use After Scope)

```cpp
// 示例：作用域后使用
int *ptr;
{
    int x = 42;
    ptr = &x;
}
*ptr = 100;  // 错误：x 已超出作用域
```

### 6. 全局缓冲区溢出 (Global Buffer Overflow)

```cpp
// 示例：全局缓冲区溢出
int global_array[100];

void foo() {
    global_array[100] = 42;  // 错误：越界访问全局数组
}
```

### 7. 双重释放 (Double Free)

```cpp
// 示例：双重释放
int *ptr = new int(42);
delete ptr;
delete ptr;  // 错误：重复释放
```

### 8. 无效释放 (Invalid Free)

```cpp
// 示例：无效释放
int stack_var = 42;
delete &stack_var;  // 错误：释放栈内存
```

---

## 代码示例

### 完整的测试程序

创建文件 `hwasan_demo.cpp`:

```cpp
#include <iostream>
#include <cstring>
#include <cstdlib>

// 1. 堆缓冲区溢出示例
void heap_buffer_overflow() {
    std::cout << "=== Testing Heap Buffer Overflow ===" << std::endl;
    int *array = new int[10];
    for (int i = 0; i < 10; i++) {
        array[i] = i;
    }
    // 错误：越界写入
    array[10] = 42;
    delete[] array;
}

// 2. 释放后使用示例
void use_after_free() {
    std::cout << "=== Testing Use After Free ===" << std::endl;
    int *ptr = new int(42);
    std::cout << "Before free: " << *ptr << std::endl;
    delete ptr;
    // 错误：使用已释放的内存
    std::cout << "After free: " << *ptr << std::endl;
}

// 3. 栈缓冲区溢出示例
void stack_buffer_overflow() {
    std::cout << "=== Testing Stack Buffer Overflow ===" << std::endl;
    char buffer[64];
    // 错误：写入超过缓冲区大小
    memset(buffer, 'A', 128);
}

// 4. 返回后使用栈内存
int* use_after_return_helper() {
    int local_array[10];
    for (int i = 0; i < 10; i++) {
        local_array[i] = i * 10;
    }
    return local_array;  // 危险：返回局部数组地址
}

void use_after_return() {
    std::cout << "=== Testing Use After Return ===" << std::endl;
    int *ptr = use_after_return_helper();
    // 错误：使用已失效的栈内存
    std::cout << "Value: " << ptr[0] << std::endl;
}

// 5. 双重释放
void double_free() {
    std::cout << "=== Testing Double Free ===" << std::endl;
    int *ptr = new int(100);
    delete ptr;
    // 错误：重复释放
    delete ptr;
}

// 主函数 - 选择测试类型
int main(int argc, char *argv[]) {
    if (argc < 2) {
        std::cout << "Usage: " << argv[0] << " <test_number>" << std::endl;
        std::cout << "  1 - Heap Buffer Overflow" << std::endl;
        std::cout << "  2 - Use After Free" << std::endl;
        std::cout << "  3 - Stack Buffer Overflow" << std::endl;
        std::cout << "  4 - Use After Return" << std::endl;
        std::cout << "  5 - Double Free" << std::endl;
        return 1;
    }

    int test_num = std::atoi(argv[1]);
    
    switch (test_num) {
        case 1: heap_buffer_overflow(); break;
        case 2: use_after_free(); break;
        case 3: stack_buffer_overflow(); break;
        case 4: use_after_return(); break;
        case 5: double_free(); break;
        default:
            std::cout << "Invalid test number: " << test_num << std::endl;
            return 1;
    }

    return 0;
}
```

### 编译和运行

```bash
# 编译
clang++ -fsanitize=hwaddress -fno-omit-frame-pointer -g -O1 \
        -o hwasan_demo hwasan_demo.cpp

# 运行各种测试
./hwasan_demo 1  # 测试堆缓冲区溢出
./hwasan_demo 2  # 测试释放后使用
./hwasan_demo 3  # 测试栈缓冲区溢出
./hwasan_demo 4  # 测试返回后使用
./hwasan_demo 5  # 测试双重释放

# 继续执行收集所有错误
HWASAN_OPTIONS="halt_on_error=0" ./hwasan_demo 1
```

---

## Android 上的使用

### 系统级 HWASan

Android 10+ 支持系统级 HWASan。构建 HWASan 系统镜像：

```bash
# 在 Android 源码目录
source build/envsetup.sh
lunch aosp_arm64-userdebug

# 构建 HWASan 版本
export SANITIZE_TARGET=hwaddress
make -j$(nproc)
```

### 应用级 HWASan

在 `Android.bp` 中启用：

```json
cc_binary {
    name: "my_app",
    srcs: ["main.cpp"],
    sanitize: {
        hwaddress: true,
    },
}
```

或在 `Android.mk` 中：

```makefile
LOCAL_SANITIZE := hwaddress
```

### NDK 使用

```bash
# 使用 NDK 的 clang 编译
$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang++ \
    -fsanitize=hwaddress \
    -fno-omit-frame-pointer \
    -g \
    -o myapp myapp.cpp
```

### Android App 集成

在 `build.gradle` 中：

```groovy
android {
    defaultConfig {
        externalNativeBuild {
            cmake {
                arguments "-DANDROID_STL=c++_shared"
                cppFlags "-fsanitize=hwaddress -fno-omit-frame-pointer"
            }
        }
    }
}
```

---

## 最佳实践

### 1. 编译建议

```bash
# 推荐的编译命令
clang++ \
    -fsanitize=hwaddress \
    -fno-omit-frame-pointer \
    -fno-optimize-sibling-calls \
    -g \
    -O1 \
    -o program program.cpp
```

### 2. 全项目启用

在 CMake 中：

```cmake
# CMakeLists.txt
option(ENABLE_HWASAN "Enable HWAddressSanitizer" OFF)

if(ENABLE_HWASAN)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=hwaddress -fno-omit-frame-pointer -g")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fsanitize=hwaddress -fno-omit-frame-pointer -g")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fsanitize=hwaddress")
endif()
```

使用：

```bash
cmake -DENABLE_HWASAN=ON ..
make
```

### 3. CI/CD 集成

```yaml
# .github/workflows/hwasan.yml
name: HWASan Tests

on: [push, pull_request]

jobs:
  hwasan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install LLVM
        run: |
          wget https://apt.llvm.org/llvm.sh
          chmod +x llvm.sh
          sudo ./llvm.sh 17
          
      - name: Build with HWASan
        run: |
          clang++-17 -fsanitize=hwaddress -g -O1 -o test_hwasan test.cpp
          
      - name: Run Tests
        run: |
          HWASAN_OPTIONS="halt_on_error=1" ./test_hwasan
```

### 4. 调试技巧

```bash
# 获取更详细的错误信息
HWASAN_OPTIONS="verbosity=2:print_stats_on_exit=1" ./program

# 保存日志到文件
HWASAN_OPTIONS="log_path=hwasan.log" ./program

# 在 GDB 中调试
HWASAN_OPTIONS="abort_on_error=1" gdb ./program

# 生成核心转储
HWASAN_OPTIONS="disable_coredump=0:abort_on_error=1" ./program
```

### 5. 性能优化

```bash
# 如果只关心堆错误，禁用栈检测以提高性能
clang++ -fsanitize=hwaddress -mllvm -hwasan-instrument-stack=0 -o program program.cpp

# 禁用读检测（只检测写操作）
clang++ -fsanitize=hwaddress -mllvm -hwasan-instrument-reads=0 -o program program.cpp
```

---

## 常见问题

### Q1: HWASan 报告 "tag-mismatch" 但代码看起来正确？

**可能原因：**
- 第三方库未使用 HWASan 编译
- 内联汇编绕过了检测
- 编译器优化导致的误报（罕见）

**解决方案：**
```bash
# 确保所有依赖都使用 HWASan 编译
# 或使用抑制规则
HWASAN_OPTIONS="suppressions=suppressions.txt" ./program
```

### Q2: 程序在 HWASan 下运行太慢？

**优化建议：**
```bash
# 使用更高优化级别
clang++ -fsanitize=hwaddress -O2 -o program program.cpp

# 禁用不必要的检测
clang++ -fsanitize=hwaddress \
        -mllvm -hwasan-instrument-stack=0 \
        -mllvm -hwasan-instrument-reads=0 \
        -o program program.cpp
```

### Q3: 如何在非 ARM64 平台上测试？

```bash
# x86_64 上使用软件模拟（实验性）
clang++ -fsanitize=hwaddress -mllvm -hwasan-use-after-scope-checking=0 \
        --target=aarch64-linux-gnu \
        -o program program.cpp

# 使用 QEMU 模拟器
qemu-aarch64 -L /usr/aarch64-linux-gnu ./program
```

### Q4: HWASan 与 ASan 能否同时使用？

**不能**。它们互斥。选择一个使用：
- 开发阶段用 ASan（更精确）
- 测试/生产阶段用 HWASan（更轻量）

### Q5: 如何解读 HWASan 的错误报告？

```
==ERROR: HWAddressSanitizer: tag-mismatch on address 0x0a1b2c3d4e5f
                                                     ↑ 标记的指针地址

WRITE of size 4 at 0x0a1b2c3d4e5f tags: 1a/00 (ptr/mem)
                                        ↑   ↑
                                        |   └── 内存中的实际 tag
                                        └────── 指针中的 tag

# 当 ptr tag ≠ mem tag 时，表示非法访问
```

### Q6: 内存中的 tag 是什么时候被改变的？

- **分配时**：分配新内存时设置随机 tag
- **释放时**：释放内存时更改为新的 tag
- **栈变量**：进入/退出作用域时更改

---

## 参考资源

- [LLVM HWAddressSanitizer 官方文档](https://clang.llvm.org/docs/HardwareAssistedAddressSanitizerDesign.html)
- [Google HWASan 设计文档](https://source.android.com/docs/security/test/hwasan)
- [Android HWASan 使用指南](https://source.android.com/docs/security/test/hwasan)
- [ARM TBI 特性说明](https://developer.arm.com/documentation/den0024/a/The-Memory-Management-Unit/The-Translation-Lookaside-Buffer)

---

## 总结

HWASan 是一个强大的内存错误检测工具，特别适合：

✅ **ARM64 平台的开发和测试**
✅ **需要在生产环境进行内存检测的场景**
✅ **对内存开销敏感的项目**
✅ **Android 应用和系统开发**

通过合理配置编译选项和运行时参数，HWASan 可以帮助开发者快速定位和修复内存相关的 bug，提高代码质量和安全性。
