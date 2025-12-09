#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANR 到 am_kill 流程分析器
分析 Android 系统中从 ANR 到进程被杀死的完整流程
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class ANREvent:
    """ANR 事件"""
    timestamp: str
    package_name: str
    pid: int
    anr_type: str  # input, service, broadcast, bg
    details: Dict


@dataclass
class KillEvent:
    """进程杀死事件"""
    timestamp: str
    package_name: str
    pid: int
    reason: str
    duration_ms: int
    importance: int


class ANRFlowAnalyzer:
    """ANR 流程分析器"""
    
    def __init__(self):
        self.anr_events: List[ANREvent] = []
        self.kill_events: List[KillEvent] = []
    
    def parse_am_kill(self, log_line: str) -> Optional[KillEvent]:
        """解析 am_kill 日志"""
        # 格式: MM-DD HH:MM:SS.microseconds  PID  TID LEVEL am_kill : [flag,pid,package,importance,reason,duration]
        pattern = r'(\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}\.\d+)\s+\d+\s+\d+\s+[VDIWEF]\s+am_kill\s*:\s*\[([^\]]+)\]'
        match = re.match(pattern, log_line.strip())
        
        if match:
            date, time, content = match.groups()
            timestamp = f"{date} {time}"
            parts = [p.strip() for p in content.split(',')]
            
            if len(parts) >= 6:
                return KillEvent(
                    timestamp=timestamp,
                    package_name=parts[2],
                    pid=int(parts[1]) if parts[1].isdigit() else 0,
                    reason=parts[4],
                    duration_ms=int(parts[5]) if parts[5].isdigit() else 0,
                    importance=int(parts[3]) if parts[3].isdigit() else 0
                )
        return None
    
    def parse_anr(self, log_line: str) -> Optional[ANREvent]:
        """解析 ANR 日志（简化版，实际需要更复杂的解析）"""
        # ANR 日志格式多样，这里提供基础框架
        if 'ANR in' in log_line or 'ANR:' in log_line:
            # 实际解析需要根据具体日志格式
            pass
        return None
    
    def analyze_flow(self, kill_event: KillEvent) -> Dict:
        """分析从 ANR 到 kill 的流程"""
        analysis = {
            'kill_event': kill_event,
            'anr_type': self._determine_anr_type(kill_event.reason),
            'time_analysis': self._analyze_timing(kill_event),
            'system_behavior': self._explain_system_behavior(kill_event),
            'possible_causes': self._suggest_causes(kill_event),
        }
        return analysis
    
    def _determine_anr_type(self, reason: str) -> str:
        """确定 ANR 类型"""
        reason_lower = reason.lower()
        if 'input' in reason_lower or 'key' in reason_lower:
            return '输入ANR (Input ANR)'
        elif 'bg anr' in reason_lower or 'background' in reason_lower:
            return '后台ANR (Background ANR)'
        elif 'service' in reason_lower:
            return '服务ANR (Service ANR)'
        elif 'broadcast' in reason_lower:
            return '广播ANR (Broadcast ANR)'
        else:
            return '未知ANR类型'
    
    def _analyze_timing(self, kill_event: KillEvent) -> Dict:
        """分析时间间隔"""
        duration_sec = kill_event.duration_ms / 1000
        duration_min = duration_sec / 60
        
        # 典型的 ANR 超时时间
        input_anr_timeout = 5  # 输入ANR: 5秒
        service_anr_timeout = 20  # 服务ANR: 20秒
        broadcast_anr_timeout = 60  # 广播ANR: 60秒
        
        # 估算 ANR 发生时间
        estimated_anr_time = duration_sec - input_anr_timeout
        
        return {
            'total_duration_seconds': duration_sec,
            'total_duration_minutes': duration_min,
            'estimated_anr_time': estimated_anr_time,
            'input_anr_timeout': input_anr_timeout,
            'kill_delay': duration_sec - input_anr_timeout,
            'timeline': self._generate_timeline(duration_sec)
        }
    
    def _generate_timeline(self, duration_sec: float) -> List[Dict]:
        """生成时间线"""
        timeline = []
        
        # T0: 用户输入
        timeline.append({
            'time': 'T0',
            'event': '用户输入事件',
            'description': '用户进行输入操作（触摸、按键等）'
        })
        
        # T0+5秒: 输入ANR检测
        timeline.append({
            'time': f'T0 + 5秒',
            'event': '系统检测到输入ANR',
            'description': '应用主线程在5秒内未响应输入事件'
        })
        
        # 中间过程
        if duration_sec > 60:
            timeline.append({
                'time': f'T0 + {int(duration_sec/2)}秒',
                'event': '应用持续无响应',
                'description': '系统监控应用状态，应用仍然无响应'
            })
        
        # 最终杀死
        timeline.append({
            'time': f'T0 + {int(duration_sec)}秒',
            'event': '系统执行 am_kill',
            'description': f'系统决定杀死进程，释放资源（已等待 {duration_sec:.1f} 秒）'
        })
        
        return timeline
    
    def _explain_system_behavior(self, kill_event: KillEvent) -> Dict:
        """解释系统行为"""
        is_background = kill_event.importance < 400
        
        explanation = {
            'is_background': is_background,
            'importance_level': kill_event.importance,
            'importance_desc': self._get_importance_description(kill_event.importance),
            'kill_reason': kill_event.reason,
            'system_strategy': ''
        }
        
        if is_background:
            explanation['system_strategy'] = (
                "后台应用ANR处理策略：\n"
                "1. 系统检测到后台应用长时间无响应\n"
                "2. 系统不会显示ANR对话框（用户不可见）\n"
                "3. 系统等待一段时间，给应用恢复机会\n"
                "4. 超过阈值后，系统直接杀死进程以释放资源\n"
                "5. 这是正常的系统保护机制"
            )
        else:
            explanation['system_strategy'] = (
                "前台应用ANR处理策略：\n"
                "1. 系统检测到前台应用无响应\n"
                "2. 系统显示ANR对话框给用户\n"
                "3. 用户可以选择等待或强制关闭\n"
                "4. 如果用户选择等待但应用持续无响应，系统可能杀死进程"
            )
        
        return explanation
    
    def _get_importance_description(self, importance: int) -> str:
        """获取重要性描述"""
        if importance >= 400:
            return "前台应用 (Foreground App)"
        elif importance >= 300:
            return "可见但不可交互 (Visible but not interactive)"
        elif importance >= 200:
            return "后台服务 (Background Service)"
        elif importance >= 100:
            return "后台应用 (Background App)"
        else:
            return "空进程 (Empty Process)"
    
    def _suggest_causes(self, kill_event: KillEvent) -> List[str]:
        """建议可能的原因"""
        causes = [
            "主线程阻塞：应用主线程被长时间阻塞（死锁、无限循环、同步等待等）",
            "资源竞争：应用在等待某个资源（文件锁、数据库锁、网络连接等），但该资源被其他进程占用",
            "内存问题：应用内存不足，导致频繁GC或接近OOM，影响响应速度",
            "系统负载：系统整体负载高，应用无法获得足够的CPU时间片来响应",
            "代码缺陷：应用代码中存在bug，导致无法正常响应或恢复",
            "第三方库问题：使用的第三方库存在性能问题或死锁",
            "数据库操作：长时间运行的数据库查询或事务未提交",
            "网络请求：网络请求超时或阻塞，导致主线程等待"
        ]
        return causes
    
    def format_analysis(self, analysis: Dict) -> str:
        """格式化分析结果"""
        output = []
        output.append("=" * 70)
        output.append("ANR 到 am_kill 流程分析")
        output.append("=" * 70)
        
        kill_event = analysis['kill_event']
        output.append(f"\n【进程杀死事件】")
        output.append(f"  时间戳: {kill_event.timestamp}")
        output.append(f"  应用包名: {kill_event.package_name}")
        output.append(f"  进程ID: {kill_event.pid}")
        output.append(f"  重要性: {kill_event.importance} ({analysis['system_behavior']['importance_desc']})")
        output.append(f"  原因: {kill_event.reason}")
        output.append(f"  持续时间: {kill_event.duration_ms} ms ({kill_event.duration_ms/1000:.2f} 秒)")
        
        output.append(f"\n【ANR 类型】")
        output.append(f"  {analysis['anr_type']}")
        
        output.append(f"\n【时间分析】")
        time_info = analysis['time_analysis']
        output.append(f"  总持续时间: {time_info['total_duration_seconds']:.2f} 秒 ({time_info['total_duration_minutes']:.2f} 分钟)")
        output.append(f"  输入ANR超时: {time_info['input_anr_timeout']} 秒")
        output.append(f"  从ANR到杀死: {time_info['kill_delay']:.2f} 秒 ({time_info['kill_delay']/60:.2f} 分钟)")
        
        output.append(f"\n【时间线】")
        for event in time_info['timeline']:
            output.append(f"  {event['time']}: {event['event']}")
            output.append(f"    └─ {event['description']}")
        
        output.append(f"\n【系统行为解释】")
        behavior = analysis['system_behavior']
        output.append(f"  应用类型: {'后台应用' if behavior['is_background'] else '前台应用'}")
        output.append(f"  系统策略:")
        for line in behavior['system_strategy'].split('\n'):
            if line.strip():
                output.append(f"    {line}")
        
        output.append(f"\n【可能的原因】")
        for i, cause in enumerate(analysis['possible_causes'], 1):
            output.append(f"  {i}. {cause}")
        
        output.append(f"\n【关键结论】")
        output.append("  1. 输入ANR在用户操作后5秒内被检测到")
        output.append(f"  2. 系统等待了约 {time_info['kill_delay']:.1f} 秒，给应用恢复机会")
        output.append("  3. 应用在这段时间内持续无响应")
        output.append("  4. 系统最终决定杀死进程以释放资源")
        output.append("  5. 这是Android系统的正常保护机制，用于维护系统稳定性")
        
        output.append("=" * 70)
        return "\n".join(output)


def main():
    """主函数"""
    # 示例日志
    log_line = "12-02 12:33:24.140988  2188 18274 I am_kill : [0,16920,com.ss.android.ugc.aweme,200,bg anr,563460]"
    
    analyzer = ANRFlowAnalyzer()
    kill_event = analyzer.parse_am_kill(log_line)
    
    if kill_event:
        analysis = analyzer.analyze_flow(kill_event)
        print(analyzer.format_analysis(analysis))
    else:
        print("无法解析日志格式")


if __name__ == '__main__':
    main()
