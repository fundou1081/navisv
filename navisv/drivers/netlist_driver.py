"""
slang-netlist driver - 调用 slang-netlist 工具生成 netlist JSON

主要功能：
- 生成 netlist JSON（节点+边）
- 生成 DOT 图
- 报告寄存器
- 报告组合环路
- Fan-in/Fan-out 分析
- 路径跟踪
"""

import subprocess
import os
import json
from typing import List, Optional, Dict, Any


# slang-netlist 工具路径
from navisv.config import NETLIST_BIN


class NetlistDriver:
    """封装 slang-netlist 工具调用"""
    
    def __init__(self, files: List[str],
                 output_dir: Optional[str] = None,
                 std: str = '1800-2017',
                 include_dirs: Optional[List[str]] = None,
                 defines: Optional[Dict[str, str]] = None,
                 top: Optional[str] = None,
                 params: Optional[Dict[str, str]] = None):
        """
        Args:
            files: 要分析的文件列表
            output_dir: 输出目录
            std: Verilog/SystemVerilog 标准
            include_dirs: include 搜索路径
            defines: 宏定义
            top: 顶层模块名
            params: 参数覆盖
        """
        self.files = files
        self.output_dir = output_dir or f'/tmp/navisv_netlist_{os.getpid()}'
        self.std = std
        self.include_dirs = include_dirs or []
        self.defines = defines or {}
        self.top = top
        self.params = params or {}
    
    def _build_cmd(self, extra_args: Optional[List[str]] = None) -> List[str]:
        """构建命令"""
        cmd = [NETLIST_BIN]
        
        # 语言标准
        cmd.extend(['--std', self.std])
        
        # Include 路径
        for inc_dir in self.include_dirs:
            cmd.extend(['-I', inc_dir])
        
        # 宏定义
        for macro, value in self.defines.items():
            if value:
                cmd.extend(['-D', f'{macro}={value}'])
            else:
                cmd.extend(['-D', macro])
        
        # 顶层模块
        if self.top:
            cmd.extend(['--top', self.top])
        
        # 参数覆盖
        for name, value in self.params.items():
            cmd.extend(['-G', f'{name}={value}'])
        
        # 额外参数
        if extra_args:
            cmd.extend(extra_args)
        
        # 源文件
        cmd.extend(self.files)
        
        return cmd
    
    def run(self, scope: Optional[str] = None) -> Dict[str, Any]:
        """
        执行 slang-netlist 生成 netlist JSON
        
        Args:
            scope: 可选，限制分析到指定模块路径
                  注意：slang-netlist 使用 --black-box 来排除其他模块
        
        Returns:
            dict: {
                'netlist_json': str,   # Netlist JSON 文件路径
                'stdout': str,
                'stderr': str,
                'returncode': int,
                'success': bool,
                'scope': str,
                'json_size': int
            }
        """
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 使用 scope 时的输出文件
        if scope:
            # 用 black-box 排除其他，只保留 scope 内的模块
            netlist_json = os.path.join(self.output_dir, f'netlist_{scope.replace(".", "_")}.json')
            cmd = self._build_cmd(['--save-netlist', netlist_json, '--black-box', f'!{scope}'])
        else:
            netlist_json = os.path.join(self.output_dir, 'netlist.json')
            cmd = self._build_cmd(['--save-netlist', netlist_json])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        return {
            'netlist_json': netlist_json if result.returncode == 0 else None,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
            'success': result.returncode == 0,
            'scope': scope,
            'json_size': os.path.getsize(netlist_json) if os.path.exists(netlist_json) else 0
        }
    
    def run_report_registers(self) -> Dict[str, Any]:
        """报告所有寄存器"""
        cmd = self._build_cmd(['--report-registers', '--stats'])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 解析寄存器列表
        registers = []
        in_section = False
        for line in result.stdout.split('\n'):
            if 'Name' in line and 'Location' in line:
                in_section = True
                continue
            if in_section and line.strip():
                parts = line.split()
                if parts:
                    registers.append({
                        'name': parts[0] if parts else '',
                        'location': ' '.join(parts[1:]) if len(parts) > 1 else ''
                    })
        
        return {
            'registers': registers,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_comb_loops(self) -> Dict[str, Any]:
        """报告组合逻辑环路"""
        cmd = self._build_cmd(['--comb-loops'])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 解析环路
        loops = []
        current_loop = []
        
        for line in result.stdout.split('\n'):
            if 'Combinational loop detected' in line:
                if current_loop:
                    loops.append(current_loop)
                current_loop = []
            elif ': note:' in line and current_loop is not None:
                current_loop.append(line.split(': note:')[0].strip())
        
        if current_loop:
            loops.append(current_loop)
        
        return {
            'comb_loops': loops,
            'count': len(loops),
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_fan_in(self, signal_path: str) -> Dict[str, Any]:
        """扇入分析"""
        cmd = self._build_cmd(['--fan-in', signal_path])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 解析 fan-in 结果
        signals = []
        in_section = False
        for line in result.stdout.split('\n'):
            if 'Name' in line and 'Location' in line:
                in_section = True
                continue
            if in_section and line.strip():
                signals.append(line.strip())
        
        return {
            'signal': signal_path,
            'fan_in': signals,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_fan_out(self, signal_path: str) -> Dict[str, Any]:
        """扇出分析"""
        cmd = self._build_cmd(['--fan-out', signal_path])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 解析 fan-out 结果
        signals = []
        in_section = False
        for line in result.stdout.split('\n'):
            if 'Name' in line and 'Location' in line:
                in_section = True
                continue
            if in_section and line.strip():
                signals.append(line.strip())
        
        return {
            'signal': signal_path,
            'fan_out': signals,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_path_trace(self, from_signal: str, to_signal: str) -> Dict[str, Any]:
        """路径跟踪"""
        cmd = self._build_cmd([
            '--from', from_signal,
            '--to', to_signal
        ])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return {
            'from': from_signal,
            'to': to_signal,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_find(self, pattern: str) -> Dict[str, Any]:
        """通配符查找节点"""
        cmd = self._build_cmd(['--find', pattern])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 解析结果
        nodes = []
        in_section = False
        for line in result.stdout.split('\n'):
            if 'Name' in line and 'Location' in line:
                in_section = True
                continue
            if in_section and line.strip():
                nodes.append(line.strip())
        
        return {
            'pattern': pattern,
            'nodes': nodes,
            'count': len(nodes),
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_dot(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """导出 DOT 格式"""
        if not output_path:
            output_path = os.path.join(self.output_dir, 'netlist.dot')
        
        cmd = self._build_cmd(['--netlist-dot', output_path])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return {
            'dot_file': output_path if os.path.exists(output_path) else None,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_stats(self) -> Dict[str, Any]:
        """执行统计"""
        cmd = self._build_cmd(['--stats'])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    @staticmethod
    def check_available() -> bool:
        """检查 slang-netlist 是否可用"""
        return os.path.isfile(NETLIST_BIN) and os.access(NETLIST_BIN, os.X_OK)
    
    @staticmethod
    def get_version() -> Optional[str]:
        """获取 slang-netlist 版本"""
        try:
            result = subprocess.run([NETLIST_BIN, '--version'],
                                   capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None


if __name__ == '__main__':
    print(f'NetlistDriver available: {NetlistDriver.check_available()}')
    print(f'Version: {NetlistDriver.get_version()}')
    
    # 测试运行
    test_file = os.path.expanduser('~/my_dv_proj/chipsonar/slang_test/design.sv')
    if os.path.exists(test_file):
        driver = NetlistDriver([test_file])
        
        print('\n--- run() ---')
        result = driver.run()
        print(f'Success: {result["success"]}')
        print(f'Netlist JSON: {result["netlist_json"]}')
        
        print('\n--- run_report_registers() ---')
        regs = driver.run_report_registers()
        print(f'Registers: {regs["registers"]}')
        
        print('\n--- run_find("*") ---')
        find = driver.run_find('*')
        print(f'Found {find["count"]} nodes')
        
        print('\n--- run_fan_in(top.alu_inst.result) ---')
        fan_in = driver.run_fan_in('top.alu_inst.result')
        print(f'Fan-in: {fan_in["fan_in"]}')