/**
 * 微信 Native Crash 注入脚本 (Frida)
 * 
 * 用途：安全测试、崩溃处理机制测试、稳定性测试
 * 
 * 使用方法：
 *   frida -U -f com.tencent.mm -l wechat_native_crash.js --no-pause
 *   或
 *   frida -U com.tencent.mm -l wechat_native_crash.js
 */

'use strict';

// ==================== 配置选项 ====================
const CONFIG = {
    // 延迟触发时间（毫秒），给应用启动留时间
    triggerDelay: 5000,
    
    // 是否自动触发 crash（设为 false 则需要手动调用）
    autoTrigger: false,
    
    // crash 类型: 'null_pointer', 'abort', 'segfault', 'stack_overflow', 'custom'
    crashType: 'null_pointer',
    
    // 是否打印详细日志
    verbose: true
};

// ==================== 日志工具 ====================
const log = {
    info: (msg) => console.log(`[*] ${msg}`),
    success: (msg) => console.log(`[+] ${msg}`),
    error: (msg) => console.log(`[-] ${msg}`),
    debug: (msg) => CONFIG.verbose && console.log(`[D] ${msg}`)
};

// ==================== Crash 触发器 ====================
const CrashTrigger = {
    
    /**
     * 空指针解引用 - 最常见的 Native Crash 类型
     */
    nullPointer: function() {
        log.info("触发空指针解引用崩溃...");
        
        const nullptr = ptr(0x0);
        try {
            // 尝试读取空指针地址
            Memory.readPointer(nullptr);
        } catch (e) {
            // Frida 会捕获异常，需要用 NativeFunction 来真正触发
            log.debug("直接读取被 Frida 捕获，尝试通过 native 调用触发");
        }
        
        // 通过调用 libc 的方式触发真正的 crash
        const libc = Process.getModuleByName("libc.so");
        const memcpy = new NativeFunction(
            libc.getExportByName("memcpy"),
            'pointer',
            ['pointer', 'pointer', 'size_t']
        );
        
        // 将数据复制到空地址会触发 SIGSEGV
        const src = Memory.alloc(16);
        Memory.writeByteArray(src, [0x41, 0x42, 0x43, 0x44]);
        
        log.info("执行非法内存操作...");
        memcpy(ptr(0x0), src, 16);
    },
    
    /**
     * 调用 abort() - 触发 SIGABRT
     */
    abort: function() {
        log.info("触发 abort() 崩溃...");
        
        const libc = Process.getModuleByName("libc.so");
        const abort = new NativeFunction(
            libc.getExportByName("abort"),
            'void',
            []
        );
        
        abort();
    },
    
    /**
     * 段错误 - 访问非法内存地址
     */
    segfault: function() {
        log.info("触发段错误崩溃...");
        
        const libc = Process.getModuleByName("libc.so");
        const memset = new NativeFunction(
            libc.getExportByName("memset"),
            'pointer',
            ['pointer', 'int', 'size_t']
        );
        
        // 写入不可访问的内存区域
        const invalidAddr = ptr("0xDEADBEEF");
        memset(invalidAddr, 0x41, 1024);
    },
    
    /**
     * 栈溢出 - 通过递归调用触发
     */
    stackOverflow: function() {
        log.info("触发栈溢出崩溃...");
        
        // 创建一个递归调用的 native 函数
        const code = Memory.alloc(Process.pageSize);
        Memory.patchCode(code, 64, function(code) {
            const writer = new Arm64Writer(code);
            // 无限递归调用自己
            writer.putBlImm(code);
            writer.flush();
        });
        
        const recursiveFunc = new NativeFunction(code, 'void', []);
        recursiveFunc();
    },
    
    /**
     * 自定义 crash - 通过 raise() 发送信号
     */
    customSignal: function(signal) {
        signal = signal || 11; // 默认 SIGSEGV
        log.info(`触发自定义信号 ${signal} 崩溃...`);
        
        const libc = Process.getModuleByName("libc.so");
        const raise = new NativeFunction(
            libc.getExportByName("raise"),
            'int',
            ['int']
        );
        
        raise(signal);
    },
    
    /**
     * 除零错误 - SIGFPE
     */
    divideByZero: function() {
        log.info("触发除零错误崩溃...");
        
        // 创建执行除零操作的 native 代码
        const code = Memory.alloc(Process.pageSize);
        
        if (Process.arch === 'arm64') {
            Memory.patchCode(code, 64, function(code) {
                const writer = new Arm64Writer(code);
                writer.putMovRegReg('x0', 'xzr');  // x0 = 0
                writer.putMovRegReg('x1', 'xzr');  // x1 = 0
                // ARM64 整数除法不会触发异常，需要使用其他方式
                writer.putBrkImm(1);  // 触发调试断点
                writer.flush();
            });
        } else if (Process.arch === 'arm') {
            Memory.patchCode(code, 64, function(code) {
                const writer = new ArmWriter(code);
                writer.putBkptImm(0);
                writer.flush();
            });
        }
        
        const divFunc = new NativeFunction(code, 'void', []);
        divFunc();
    }
};

// ==================== 微信特定 Hook ====================
const WeChatHooks = {
    
    /**
     * Hook 微信的 crash 处理函数
     */
    hookCrashHandler: function() {
        log.info("尝试 hook 微信崩溃处理器...");
        
        // 微信常见的 crash 处理库
        const crashLibs = [
            "libwechatcrash.so",
            "libcrashlytics.so", 
            "libxcrash.so",
            "libwechatxlog.so"
        ];
        
        crashLibs.forEach(libName => {
            try {
                const lib = Process.getModuleByName(libName);
                if (lib) {
                    log.success(`找到 ${libName} @ ${lib.base}`);
                    this.hookLibraryExports(lib);
                }
            } catch (e) {
                log.debug(`${libName} 未加载`);
            }
        });
    },
    
    /**
     * Hook 库的导出函数
     */
    hookLibraryExports: function(lib) {
        const exports = lib.enumerateExports();
        
        exports.forEach(exp => {
            // 寻找 crash 相关的函数
            if (exp.name.toLowerCase().includes('crash') ||
                exp.name.toLowerCase().includes('signal') ||
                exp.name.toLowerCase().includes('exception')) {
                
                log.debug(`发现目标函数: ${exp.name}`);
                
                try {
                    Interceptor.attach(exp.address, {
                        onEnter: function(args) {
                            log.info(`[HOOK] ${exp.name} 被调用`);
                            log.debug(`  参数: ${args[0]}, ${args[1]}, ${args[2]}`);
                        },
                        onLeave: function(retval) {
                            log.debug(`  返回值: ${retval}`);
                        }
                    });
                } catch (e) {
                    log.error(`Hook ${exp.name} 失败: ${e}`);
                }
            }
        });
    },
    
    /**
     * Hook 信号处理
     */
    hookSignalHandler: function() {
        log.info("Hook 信号处理函数...");
        
        const libc = Process.getModuleByName("libc.so");
        const signal = libc.getExportByName("signal");
        const sigaction = libc.getExportByName("sigaction");
        
        if (signal) {
            Interceptor.attach(signal, {
                onEnter: function(args) {
                    const signum = args[0].toInt32();
                    const handler = args[1];
                    log.info(`[signal] 注册信号 ${signum} 处理器 @ ${handler}`);
                }
            });
        }
        
        if (sigaction) {
            Interceptor.attach(sigaction, {
                onEnter: function(args) {
                    const signum = args[0].toInt32();
                    log.info(`[sigaction] 注册信号 ${signum} 处理器`);
                }
            });
        }
    }
};

// ==================== 主控制接口 ====================
const Controller = {
    
    /**
     * 触发 crash
     */
    crash: function(type) {
        type = type || CONFIG.crashType;
        log.success(`准备触发 ${type} 类型的 crash`);
        
        switch (type) {
            case 'null_pointer':
                CrashTrigger.nullPointer();
                break;
            case 'abort':
                CrashTrigger.abort();
                break;
            case 'segfault':
                CrashTrigger.segfault();
                break;
            case 'stack_overflow':
                CrashTrigger.stackOverflow();
                break;
            case 'divide_zero':
                CrashTrigger.divideByZero();
                break;
            case 'sigkill':
                CrashTrigger.customSignal(9);
                break;
            case 'sigabrt':
                CrashTrigger.customSignal(6);
                break;
            case 'sigsegv':
                CrashTrigger.customSignal(11);
                break;
            default:
                log.error(`未知的 crash 类型: ${type}`);
        }
    },
    
    /**
     * 显示帮助信息
     */
    help: function() {
        console.log(`
========================================
   微信 Native Crash 注入工具
========================================

可用命令 (在 Frida 控制台中调用):

  crash()              - 使用默认方式触发 crash
  crash('abort')       - 触发 abort() crash
  crash('null_pointer') - 触发空指针 crash
  crash('segfault')    - 触发段错误 crash
  crash('stack_overflow') - 触发栈溢出 crash
  crash('divide_zero') - 触发除零错误
  crash('sigkill')     - 发送 SIGKILL 信号
  crash('sigabrt')     - 发送 SIGABRT 信号
  crash('sigsegv')     - 发送 SIGSEGV 信号
  
  listModules()        - 列出已加载的模块
  findCrashLib()       - 查找 crash 相关的库
  help()               - 显示此帮助

========================================
        `);
    },
    
    /**
     * 列出加载的模块
     */
    listModules: function() {
        log.info("已加载的模块:");
        Process.enumerateModules().forEach(m => {
            if (m.name.includes('wechat') || m.name.includes('tencent')) {
                log.success(`${m.name} @ ${m.base} (${m.size})`);
            }
        });
    },
    
    /**
     * 查找 crash 相关库
     */
    findCrashLib: function() {
        log.info("搜索 crash 相关的库...");
        Process.enumerateModules().forEach(m => {
            const name = m.name.toLowerCase();
            if (name.includes('crash') || name.includes('xlog') || 
                name.includes('bugly') || name.includes('breakpad')) {
                log.success(`找到: ${m.name} @ ${m.base}`);
            }
        });
    }
};

// ==================== 导出到全局 ====================
global.crash = Controller.crash;
global.help = Controller.help;
global.listModules = Controller.listModules;
global.findCrashLib = Controller.findCrashLib;
global.CrashTrigger = CrashTrigger;
global.WeChatHooks = WeChatHooks;

// ==================== 初始化 ====================
function init() {
    log.success("微信 Native Crash 注入脚本已加载");
    log.info(`进程: ${Process.id}`);
    log.info(`架构: ${Process.arch}`);
    log.info(`平台: ${Process.platform}`);
    
    // 设置 hook
    Java.perform(function() {
        log.success("Java VM 已就绪");
        
        // Hook 微信的 crash 处理
        WeChatHooks.hookCrashHandler();
        WeChatHooks.hookSignalHandler();
    });
    
    // 显示帮助
    Controller.help();
    
    // 自动触发（如果配置了）
    if (CONFIG.autoTrigger) {
        log.info(`将在 ${CONFIG.triggerDelay}ms 后自动触发 crash...`);
        setTimeout(function() {
            Controller.crash();
        }, CONFIG.triggerDelay);
    }
}

// 延迟初始化，等待模块加载
setTimeout(init, 1000);
