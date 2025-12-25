/**
 * HWASan (Hardware-assisted AddressSanitizer) 演示程序
 * 
 * 编译命令 (需要 ARM64 平台):
 *   clang++ -fsanitize=hwaddress -fno-omit-frame-pointer -g -O1 -o hwasan_demo hwasan_demo.cpp
 * 
 * 运行:
 *   ./hwasan_demo <test_number>
 * 
 * 带选项运行:
 *   HWASAN_OPTIONS="halt_on_error=0:verbosity=1" ./hwasan_demo <test_number>
 */

#include <iostream>
#include <cstring>
#include <cstdlib>

//=============================================================================
// 测试 1: 堆缓冲区溢出 (Heap Buffer Overflow)
//=============================================================================
void test_heap_buffer_overflow() {
    std::cout << "\n=== 测试: 堆缓冲区溢出 (Heap Buffer Overflow) ===" << std::endl;
    std::cout << "分配 10 个 int 的数组，然后访问第 11 个元素..." << std::endl;
    
    int *array = new int[10];
    
    // 正常初始化
    for (int i = 0; i < 10; i++) {
        array[i] = i * 10;
    }
    
    std::cout << "正常访问 array[9] = " << array[9] << std::endl;
    
    // 错误：越界写入
    std::cout << "尝试写入 array[10]... (这是越界访问)" << std::endl;
    array[10] = 42;  // HWASan 将在这里报错
    
    delete[] array;
    std::cout << "如果你看到这行，说明 HWASan 未检测到错误" << std::endl;
}

//=============================================================================
// 测试 2: 释放后使用 (Use After Free)
//=============================================================================
void test_use_after_free() {
    std::cout << "\n=== 测试: 释放后使用 (Use After Free) ===" << std::endl;
    std::cout << "分配内存，释放后再访问..." << std::endl;
    
    int *ptr = new int(42);
    std::cout << "分配后的值: " << *ptr << std::endl;
    
    delete ptr;
    std::cout << "内存已释放" << std::endl;
    
    // 错误：使用已释放的内存
    std::cout << "尝试读取已释放的内存..." << std::endl;
    int value = *ptr;  // HWASan 将在这里报错
    std::cout << "读取到的值: " << value << std::endl;
}

//=============================================================================
// 测试 3: 栈缓冲区溢出 (Stack Buffer Overflow)
//=============================================================================
void test_stack_buffer_overflow() {
    std::cout << "\n=== 测试: 栈缓冲区溢出 (Stack Buffer Overflow) ===" << std::endl;
    std::cout << "创建 64 字节的栈缓冲区，然后写入 128 字节..." << std::endl;
    
    char buffer[64];
    
    // 正常使用
    memset(buffer, 'A', 60);
    buffer[60] = '\0';
    std::cout << "正常填充 60 字节: OK" << std::endl;
    
    // 错误：写入超过缓冲区大小
    std::cout << "尝试写入 128 字节... (这是栈溢出)" << std::endl;
    memset(buffer, 'B', 128);  // HWASan 将在这里报错
    
    std::cout << "如果你看到这行，说明 HWASan 未检测到错误" << std::endl;
}

//=============================================================================
// 测试 4: 返回后使用栈内存 (Use After Return)
//=============================================================================
__attribute__((noinline))
int* get_local_array() {
    int local_array[10];
    for (int i = 0; i < 10; i++) {
        local_array[i] = i * 100;
    }
    std::cout << "在函数内部，local_array[5] = " << local_array[5] << std::endl;
    return local_array;  // 警告：返回局部变量地址
}

void test_use_after_return() {
    std::cout << "\n=== 测试: 返回后使用栈内存 (Use After Return) ===" << std::endl;
    std::cout << "调用函数返回局部数组的地址，然后访问..." << std::endl;
    
    int *ptr = get_local_array();
    
    // 错误：使用已失效的栈内存
    std::cout << "尝试访问已返回函数的局部变量..." << std::endl;
    std::cout << "ptr[5] = " << ptr[5] << std::endl;  // HWASan 可能在这里报错
}

//=============================================================================
// 测试 5: 双重释放 (Double Free)
//=============================================================================
void test_double_free() {
    std::cout << "\n=== 测试: 双重释放 (Double Free) ===" << std::endl;
    std::cout << "分配内存，释放两次..." << std::endl;
    
    int *ptr = new int(100);
    std::cout << "分配的值: " << *ptr << std::endl;
    
    delete ptr;
    std::cout << "第一次释放: OK" << std::endl;
    
    // 错误：重复释放
    std::cout << "尝试第二次释放... (这是双重释放)" << std::endl;
    delete ptr;  // HWASan 将在这里报错
    
    std::cout << "如果你看到这行，说明 HWASan 未检测到错误" << std::endl;
}

//=============================================================================
// 测试 6: 作用域后使用 (Use After Scope)
//=============================================================================
void test_use_after_scope() {
    std::cout << "\n=== 测试: 作用域后使用 (Use After Scope) ===" << std::endl;
    std::cout << "在内部作用域创建变量，离开后访问..." << std::endl;
    
    int *ptr = nullptr;
    
    {
        int inner_var = 12345;
        ptr = &inner_var;
        std::cout << "在作用域内，*ptr = " << *ptr << std::endl;
    }
    // inner_var 已超出作用域
    
    // 错误：访问已超出作用域的变量
    std::cout << "尝试访问已超出作用域的变量..." << std::endl;
    std::cout << "*ptr = " << *ptr << std::endl;  // HWASan 可能在这里报错
}

//=============================================================================
// 测试 7: 堆缓冲区下溢 (Heap Buffer Underflow)
//=============================================================================
void test_heap_buffer_underflow() {
    std::cout << "\n=== 测试: 堆缓冲区下溢 (Heap Buffer Underflow) ===" << std::endl;
    std::cout << "分配数组，然后访问 index -1..." << std::endl;
    
    int *array = new int[10];
    
    for (int i = 0; i < 10; i++) {
        array[i] = i;
    }
    
    // 错误：下溢访问
    std::cout << "尝试访问 array[-1]... (这是下溢)" << std::endl;
    array[-1] = 999;  // HWASan 将在这里报错
    
    delete[] array;
}

//=============================================================================
// 测试 8: 部分越界读取
//=============================================================================
void test_partial_oob_read() {
    std::cout << "\n=== 测试: 部分越界读取 ===" << std::endl;
    std::cout << "分配 10 字节，尝试读取 8 字节从偏移 5 开始..." << std::endl;
    
    char *buffer = new char[10];
    memset(buffer, 'X', 10);
    
    // 错误：读取会超出边界 (5 + 8 = 13 > 10)
    std::cout << "尝试 memcpy 从偏移 5 读取 8 字节..." << std::endl;
    char dest[8];
    memcpy(dest, buffer + 5, 8);  // HWASan 将在这里报错
    
    delete[] buffer;
}

//=============================================================================
// 主函数
//=============================================================================
void print_usage(const char *program_name) {
    std::cout << "\nHWASan 演示程序" << std::endl;
    std::cout << "================\n" << std::endl;
    std::cout << "用法: " << program_name << " <测试编号>\n" << std::endl;
    std::cout << "可用的测试:" << std::endl;
    std::cout << "  1 - 堆缓冲区溢出 (Heap Buffer Overflow)" << std::endl;
    std::cout << "  2 - 释放后使用 (Use After Free)" << std::endl;
    std::cout << "  3 - 栈缓冲区溢出 (Stack Buffer Overflow)" << std::endl;
    std::cout << "  4 - 返回后使用栈内存 (Use After Return)" << std::endl;
    std::cout << "  5 - 双重释放 (Double Free)" << std::endl;
    std::cout << "  6 - 作用域后使用 (Use After Scope)" << std::endl;
    std::cout << "  7 - 堆缓冲区下溢 (Heap Buffer Underflow)" << std::endl;
    std::cout << "  8 - 部分越界读取 (Partial OOB Read)" << std::endl;
    std::cout << "\n编译命令 (ARM64):" << std::endl;
    std::cout << "  clang++ -fsanitize=hwaddress -fno-omit-frame-pointer -g -O1 \\" << std::endl;
    std::cout << "          -o hwasan_demo hwasan_demo.cpp" << std::endl;
    std::cout << "\n运行时选项 (可选):" << std::endl;
    std::cout << "  HWASAN_OPTIONS=\"halt_on_error=0\" ./hwasan_demo 1" << std::endl;
    std::cout << "  HWASAN_OPTIONS=\"verbosity=2\" ./hwasan_demo 1" << std::endl;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    int test_num = std::atoi(argv[1]);
    
    std::cout << "========================================" << std::endl;
    std::cout << " HWASan 演示 - 测试 #" << test_num << std::endl;
    std::cout << "========================================" << std::endl;
    
    switch (test_num) {
        case 1: test_heap_buffer_overflow(); break;
        case 2: test_use_after_free(); break;
        case 3: test_stack_buffer_overflow(); break;
        case 4: test_use_after_return(); break;
        case 5: test_double_free(); break;
        case 6: test_use_after_scope(); break;
        case 7: test_heap_buffer_underflow(); break;
        case 8: test_partial_oob_read(); break;
        default:
            std::cout << "无效的测试编号: " << test_num << std::endl;
            print_usage(argv[0]);
            return 1;
    }

    std::cout << "\n程序正常结束" << std::endl;
    return 0;
}
