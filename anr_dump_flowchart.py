#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANR Dump Flow Chart Generator
从 ProcessErrorStateRecord 到 traces.txt 的完整流程图
"""

from graphviz import Digraph

def create_anr_dump_flowchart():
    # 创建有向图
    dot = Digraph(comment='ANR Dump Flow', format='png')
    dot.attr(rankdir='TB', size='16,24', dpi='150')
    dot.attr('node', fontname='Arial', fontsize='11')
    dot.attr('edge', fontname='Arial', fontsize='10')
    
    # ==================== Java 层 ====================
    with dot.subgraph(name='cluster_java') as java:
        java.attr(label='Java 层 (system_server)', style='rounded', 
                  bgcolor='#E3F2FD', color='#1976D2', penwidth='2')
        java.attr('node', shape='box', style='rounded,filled', fillcolor='#BBDEFB')
        
        java.node('per', 'ProcessErrorStateRecord\n.appNotResponding()\n\n收集 firstPids, lastPids\n调用 StackTracesDumpHelper')
        java.node('sth', 'StackTracesDumpHelper\n.dumpStackTraces()\n\n创建 /data/anr/traces.txt\n遍历进程列表进行 dump')
        java.node('djt', 'dumpJavaTracesTombstoned()\n\n调用 Debug native 方法')
        
        java.edge('per', 'sth')
        java.edge('sth', 'djt')
    
    # ==================== JNI 层 ====================
    with dot.subgraph(name='cluster_jni') as jni:
        jni.attr(label='JNI 层 (android_os_Debug.cpp)', style='rounded',
                 bgcolor='#FFF3E0', color='#F57C00', penwidth='2')
        jni.attr('node', shape='box', style='rounded,filled', fillcolor='#FFE0B2')
        
        jni.node('jni_dump', 'android_os_Debug_\ndumpJavaBacktraceToFileTimeout()\n\n调用 dumpTraces()')
        jni.node('dump_traces', 'dumpTraces()\n\n1. open(traces.txt, O_APPEND)\n2. getBinderTransactions() 写入\n3. dump_backtrace_to_file_timeout()')
    
        jni.edge('jni_dump', 'dump_traces')
    
    # ==================== Native 层 ====================
    with dot.subgraph(name='cluster_native') as native:
        native.attr(label='Native 层 (debuggerd_client.cpp)', style='rounded',
                    bgcolor='#E8F5E9', color='#388E3C', penwidth='2')
        native.attr('node', shape='box', style='rounded,filled', fillcolor='#C8E6C9')
        
        native.node('dbtft', 'dump_backtrace_to_file_timeout()\n\n调用 debuggerd_trigger_dump()')
        
        native.node('dtd_1', '① 获取 tgid\n\nif (kDebuggerdJavaBacktrace)\n  tid = GetProcessInfo(tid).pid')
        native.node('dtd_2', '② 创建 Socket 连接\n\nsocket(AF_LOCAL, SOCK_SEQPACKET)\nconnect(tombstoned)')
        native.node('dtd_3', '③ 创建 Pipe\n\nPipe(&pipe_read, &pipe_write)\n设置 1MB 缓冲区')
        native.node('dtd_4', '④ 发送请求\n\nSendFileDescriptors(\n  req, pipe_write)')
        native.node('dtd_5', '⑤ 等待注册确认\n\nget_response(kRegistered)')
        native.node('dtd_6', '⑥ ★ 发送 SIGQUIT ★\n\nsigqueue(tid, SIGQUIT, val)', 
                    shape='box', style='rounded,filled', fillcolor='#FFCDD2', color='#D32F2F', penwidth='3')
        native.node('dtd_7', '⑦ 等待开始确认\n\nget_response(kStarted)')
        native.node('dtd_8', '⑧ 读取 Pipe 数据\n\nwhile(true) {\n  poll(pipe_read)\n  read(pipe_read, buf)\n  WriteFully(output_fd, buf)\n}')
        
        native.edge('dbtft', 'dtd_1')
        native.edge('dtd_1', 'dtd_2')
        native.edge('dtd_2', 'dtd_3')
        native.edge('dtd_3', 'dtd_4')
        native.edge('dtd_4', 'dtd_5')
        native.edge('dtd_5', 'dtd_6')
        native.edge('dtd_6', 'dtd_7')
        native.edge('dtd_7', 'dtd_8')
    
    # ==================== tombstoned ====================
    with dot.subgraph(name='cluster_tombstoned') as tomb:
        tomb.attr(label='tombstoned 守护进程', style='rounded',
                  bgcolor='#F3E5F5', color='#7B1FA2', penwidth='2')
        tomb.attr('node', shape='box', style='rounded,filled', fillcolor='#E1BEE7')
        
        tomb.node('tomb_1', '接收 InterceptRequest\n保存 pipe_write fd')
        tomb.node('tomb_2', '发送 kRegistered')
        tomb.node('tomb_3', '将 pipe_write fd\n转发给目标进程')
        tomb.node('tomb_4', '发送 kStarted')
        
        tomb.edge('tomb_1', 'tomb_2')
        tomb.edge('tomb_2', 'tomb_3')
        tomb.edge('tomb_3', 'tomb_4')
    
    # ==================== 目标应用进程 ====================
    with dot.subgraph(name='cluster_target') as target:
        target.attr(label='目标应用进程', style='rounded',
                    bgcolor='#FFEBEE', color='#C62828', penwidth='2')
        target.attr('node', shape='box', style='rounded,filled', fillcolor='#FFCDD2')
        
        target.node('sigquit', 'SIGQUIT 信号到达', shape='oval', fillcolor='#EF9A9A')
        target.node('sigchain', 'libsigchain\n信号链分发')
        target.node('sdk', '第三方 SDK Handler\n\nreturn false → 继续传递\nreturn true → 信号被消费!', 
                    style='rounded,filled', fillcolor='#FFF9C4')
        target.node('art_sc', 'ART Signal Catcher\n\nHandleSigQuit()')
        target.node('dump_sig', 'DumpForSigQuit()\n\n- dump Java 线程堆栈\n- dump GC 信息\n- dump 锁信息')
        target.node('write_pipe', 'write(pipe_write_fd,\n       stack_trace_data)')
        
        target.edge('sigquit', 'sigchain')
        target.edge('sigchain', 'sdk')
        target.edge('sdk', 'art_sc', label='return false')
        target.edge('art_sc', 'dump_sig')
        target.edge('dump_sig', 'write_pipe')
    
    # ==================== 输出文件 ====================
    dot.node('traces', '/data/anr/traces.txt\n\n包含所有进程的\n堆栈信息', 
             shape='folder', style='filled', fillcolor='#B2DFDB', color='#00796B', penwidth='2')
    
    # ==================== 信号被截获的情况 ====================
    with dot.subgraph(name='cluster_error') as error:
        error.attr(label='⚠️ 第三方 SDK 截获信号时', style='rounded',
                   bgcolor='#FBE9E7', color='#BF360C', penwidth='2')
        error.attr('node', shape='box', style='rounded,filled', fillcolor='#FFCCBC')
        
        error.node('err_1', 'SDK handler\nreturn true\n(消费信号)')
        error.node('err_2', 'ART Signal Catcher\n收不到信号')
        error.node('err_3', 'Pipe 无数据写入')
        error.node('err_4', 'poll() 超时\ndump 失败 ✗')
        
        error.edge('err_1', 'err_2')
        error.edge('err_2', 'err_3')
        error.edge('err_3', 'err_4')
    
    # ==================== 连接各层 ====================
    # Java -> JNI
    dot.edge('djt', 'jni_dump', label='JNI 调用', style='dashed', color='#1976D2')
    
    # JNI -> Native
    dot.edge('dump_traces', 'dbtft', label='Native 调用', style='dashed', color='#F57C00')
    
    # Native <-> tombstoned
    dot.edge('dtd_4', 'tomb_1', label='socket 通信', style='dashed', color='#7B1FA2')
    dot.edge('tomb_2', 'dtd_5', style='dashed', color='#7B1FA2')
    dot.edge('tomb_4', 'dtd_7', style='dashed', color='#7B1FA2')
    
    # Native -> 目标进程 (SIGQUIT)
    dot.edge('dtd_6', 'sigquit', label='SIGQUIT (信号3)', 
             style='bold', color='#D32F2F', penwidth='2')
    
    # tombstoned -> 目标进程 (pipe fd)
    dot.edge('tomb_3', 'write_pipe', label='传递 pipe_write fd', 
             style='dashed', color='#7B1FA2')
    
    # 目标进程 -> Native (数据回传)
    dot.edge('write_pipe', 'dtd_8', label='堆栈数据\n通过 Pipe 传输', 
             style='bold', color='#388E3C', penwidth='2')
    
    # Native -> traces.txt
    dot.edge('dtd_8', 'traces', label='WriteFully()', style='bold', color='#00796B', penwidth='2')
    
    # SDK 截获情况
    dot.edge('sdk', 'err_1', label='return true', style='dashed', color='#BF360C')
    
    return dot

def create_simplified_flowchart():
    """创建简化版流程图"""
    dot = Digraph(comment='ANR Dump Flow (Simplified)', format='png')
    dot.attr(rankdir='TB', size='12,16', dpi='150')
    dot.attr('node', fontname='Arial', fontsize='12')
    dot.attr('edge', fontname='Arial', fontsize='10')
    
    # 节点定义
    dot.node('start', 'ANR 发生', shape='oval', style='filled', fillcolor='#FFCDD2')
    
    dot.node('java1', 'ProcessErrorStateRecord\n.appNotResponding()', 
             shape='box', style='rounded,filled', fillcolor='#BBDEFB')
    dot.node('java2', 'StackTracesDumpHelper\n.dumpStackTraces()', 
             shape='box', style='rounded,filled', fillcolor='#BBDEFB')
    
    dot.node('jni', 'dumpTraces()\n[JNI层]', 
             shape='box', style='rounded,filled', fillcolor='#FFE0B2')
    
    dot.node('native', 'debuggerd_trigger_dump()', 
             shape='box', style='rounded,filled', fillcolor='#C8E6C9')
    
    dot.node('signal', '★ sigqueue(pid, SIGQUIT) ★\n发送信号给目标进程', 
             shape='box', style='rounded,filled', fillcolor='#FFCDD2', 
             color='#D32F2F', penwidth='3')
    
    dot.node('target', '目标进程\n信号处理', 
             shape='box', style='rounded,filled', fillcolor='#E1BEE7')
    
    dot.node('sigchain', 'libsigchain\n信号链分发', 
             shape='box', style='rounded,filled', fillcolor='#FFF9C4')
    
    dot.node('sdk', '第三方 SDK\nHandler', 
             shape='diamond', style='filled', fillcolor='#FFCC80')
    
    dot.node('art', 'ART Signal Catcher\nHandleSigQuit()\nDumpForSigQuit()', 
             shape='box', style='rounded,filled', fillcolor='#C8E6C9')
    
    dot.node('pipe', 'write(pipe_fd, stack_data)\n通过 Pipe 传输数据', 
             shape='box', style='rounded,filled', fillcolor='#B2EBF2')
    
    dot.node('traces', '/data/anr/traces.txt', 
             shape='folder', style='filled', fillcolor='#B2DFDB')
    
    dot.node('fail', 'Dump 失败\n(超时)', 
             shape='box', style='rounded,filled', fillcolor='#FFCDD2')
    
    # 边定义
    dot.edge('start', 'java1')
    dot.edge('java1', 'java2')
    dot.edge('java2', 'jni', label='JNI')
    dot.edge('jni', 'native')
    dot.edge('native', 'signal')
    dot.edge('signal', 'target', label='SIGQUIT', color='#D32F2F', penwidth='2')
    dot.edge('target', 'sigchain')
    dot.edge('sigchain', 'sdk')
    dot.edge('sdk', 'art', label='传递信号\n(return false)', color='#388E3C')
    dot.edge('sdk', 'fail', label='截获信号\n(return true)', color='#D32F2F', style='dashed')
    dot.edge('art', 'pipe')
    dot.edge('pipe', 'native', label='数据回传', style='dashed', color='#1976D2')
    dot.edge('native', 'traces', label='写入文件', color='#00796B', penwidth='2')
    
    return dot

def create_sequence_diagram():
    """创建时序图风格的流程图"""
    dot = Digraph(comment='ANR Dump Sequence', format='png')
    dot.attr(rankdir='LR', size='20,12', dpi='150')
    dot.attr('node', fontname='Arial', fontsize='10')
    dot.attr('edge', fontname='Arial', fontsize='9')
    
    # 定义各个参与者
    with dot.subgraph(name='cluster_ams') as c:
        c.attr(label='system_server', style='rounded', bgcolor='#E3F2FD')
        c.node('ams1', 'ProcessError\nStateRecord', shape='box', style='filled', fillcolor='#BBDEFB')
        c.node('ams2', 'StackTraces\nDumpHelper', shape='box', style='filled', fillcolor='#BBDEFB')
        c.node('ams3', 'Debug\n(JNI)', shape='box', style='filled', fillcolor='#FFE0B2')
        c.node('ams4', 'debuggerd\n_client', shape='box', style='filled', fillcolor='#C8E6C9')
    
    with dot.subgraph(name='cluster_tomb') as c:
        c.attr(label='tombstoned', style='rounded', bgcolor='#F3E5F5')
        c.node('tomb', 'tombstoned\n守护进程', shape='box', style='filled', fillcolor='#E1BEE7')
    
    with dot.subgraph(name='cluster_app') as c:
        c.attr(label='目标应用', style='rounded', bgcolor='#FFEBEE')
        c.node('app1', 'libsigchain', shape='box', style='filled', fillcolor='#FFF9C4')
        c.node('app2', 'SDK Handler', shape='diamond', style='filled', fillcolor='#FFCC80')
        c.node('app3', 'ART Signal\nCatcher', shape='box', style='filled', fillcolor='#C8E6C9')
    
    dot.node('file', '/data/anr/\ntraces.txt', shape='folder', style='filled', fillcolor='#B2DFDB')
    
    # 连接
    dot.edge('ams1', 'ams2', label='1. appNotResponding()')
    dot.edge('ams2', 'ams3', label='2. dumpJavaBacktrace()')
    dot.edge('ams3', 'ams4', label='3. dump_backtrace()')
    dot.edge('ams4', 'tomb', label='4. connect & register')
    dot.edge('ams4', 'app1', label='5. SIGQUIT', color='#D32F2F', penwidth='2')
    dot.edge('tomb', 'app3', label='6. pipe_write fd', style='dashed')
    dot.edge('app1', 'app2', label='7. 分发信号')
    dot.edge('app2', 'app3', label='8. 传递', color='#388E3C')
    dot.edge('app3', 'ams4', label='9. write(pipe)', style='dashed', color='#1976D2')
    dot.edge('ams4', 'file', label='10. WriteFully()', color='#00796B', penwidth='2')
    
    return dot

if __name__ == '__main__':
    # 生成完整流程图
    print("生成完整流程图...")
    full_chart = create_anr_dump_flowchart()
    full_chart.render('/workspace/anr_dump_flowchart_full', cleanup=True)
    print("完整流程图已保存: /workspace/anr_dump_flowchart_full.png")
    
    # 生成简化版流程图
    print("\n生成简化版流程图...")
    simple_chart = create_simplified_flowchart()
    simple_chart.render('/workspace/anr_dump_flowchart_simple', cleanup=True)
    print("简化版流程图已保存: /workspace/anr_dump_flowchart_simple.png")
    
    # 生成时序图
    print("\n生成时序风格图...")
    seq_chart = create_sequence_diagram()
    seq_chart.render('/workspace/anr_dump_sequence', cleanup=True)
    print("时序图已保存: /workspace/anr_dump_sequence.png")
    
    print("\n✅ 所有流程图生成完成!")
