"""
slang driver - 调用 slang 工具生成 AST JSON

主要功能：
- 语法检查
- 生成 AST JSON
- 生成诊断 JSON
- 依赖文件生成
"""

import subprocess
import os
import json
import tempfile
from typing import List, Optional, Dict, Any


# slang 工具路径
from navisv.config import SLANG_BIN


class SlangDriver:
    """封装 slang 工具调用"""
    
    def __init__(self, files: List[str], 
                 output_dir: Optional[str] = None,
                 std: str = '1800-2017',
                 include_dirs: Optional[List[str]] = None,
                 defines: Optional[Dict[str, str]] = None,
                 top: Optional[str] = None,
                 params: Optional[Dict[str, str]] = None,
                 source_info: bool = False,
                 detailed_types: bool = False,
                 scope: Optional[str] = None):
        """
        Args:
            files: 要分析的文件列表
            output_dir: 输出目录，默认使用系统临时目录
            std: Verilog/SystemVerilog 标准 (1364-2005, 1800-2017, 1800-2023, latest)
            include_dirs: include 搜索路径
            defines: 宏定义 {'MACRO': 'value'}
            top: 顶层模块名
            params: 参数覆盖 {'PARAM_NAME': 'value'}
            source_info: 是否包含源码位置信息
            detailed_types: 是否包含详细类型信息
            scope: 限制 AST 作用域到指定路径
        """
        self.files = files
        self.output_dir = output_dir or f'/tmp/navisv_slang_{os.getpid()}'
        self.std = std
        self.include_dirs = include_dirs or []
        self.defines = defines or {}
        self.top = top
        self.params = params or {}
        self.source_info = source_info
        self.detailed_types = detailed_types
        self.scope = scope
    
    def _build_cmd(self) -> List[str]:
        """构建命令"""
        cmd = [SLANG_BIN]
        
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
        
        # AST JSON 输出
        ast_json = os.path.join(self.output_dir, 'ast.json')
        cmd.extend(['--ast-json', ast_json])
        
        # 源码信息
        if self.source_info:
            cmd.append('--ast-json-source-info')
        
        # 详细类型
        if self.detailed_types:
            cmd.append('--ast-json-detailed-types')
        
        # 作用域限制
        if self.scope:
            cmd.extend(['--ast-json-scope', self.scope])
        
        # 诊断 JSON
        diag_json = os.path.join(self.output_dir, 'diag.json')
        cmd.extend(['--diag-json', diag_json])
        
        # 源文件
        cmd.extend(self.files)
        
        return cmd
    
    def run(self, scope: Optional[str] = None) -> Dict[str, Any]:
        """
        执行 slang 生成 AST JSON
        
        Args:
            scope: 可选，限制 AST 作用域到指定路径（如 'top.cpu.alu'）
                  可以大幅减少大型设计的 JSON 大小
        
        Returns:
            dict: {
                'ast_json': str,       # AST JSON 文件路径
                'diag_json': str,      # 诊断 JSON 文件路径
                'diagnostics': list,   # 诊断信息列表
                'stdout': str,
                'stderr': str,
                'returncode': int,
                'success': bool,
                'error_count': int,
                'warning_count': int,
                'scope': str,          # 使用的 scope
                'json_size': int       # JSON 文件大小（字节）
            }
        """
        os.makedirs(self.output_dir, exist_ok=True)
        diag_json = os.path.join(self.output_dir, 'diag.json')
        
        # 使用 scope 时的输出文件
        if scope:
            ast_json = os.path.join(self.output_dir, f'ast_{scope.replace(".", "_")}.json')
        else:
            ast_json = os.path.join(self.output_dir, 'ast.json')
        
        cmd = self._build_cmd()
        
        # 更新 AST JSON 路径（如果用 scope）
        if scope:
            # 替换命令中的 ast.json 路径
            for i, arg in enumerate(cmd):
                if arg == '--ast-json' and i+1 < len(cmd):
                    cmd[i+1] = ast_json
            # 添加 scope 参数
            cmd.extend(['--ast-json-scope', scope])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        # 解析诊断
        diagnostics = []
        error_count = 0
        warning_count = 0
        
        if os.path.exists(diag_json):
            try:
                with open(diag_json) as f:
                    diag_data = json.load(f)
                    diagnostics = diag_data if isinstance(diag_data, list) else [diag_data]
                    
                for d in diagnostics:
                    if d.get('severity') == 'Error':
                        error_count += 1
                    elif d.get('severity') == 'Warning':
                        warning_count += 1
            except (json.JSONDecodeError, IOError):
                pass
        
        return {
            'ast_json': ast_json if result.returncode == 0 else None,
            'diag_json': diag_json if os.path.exists(diag_json) else None,
            'diagnostics': diagnostics,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
            'success': result.returncode == 0,
            'error_count': error_count,
            'warning_count': warning_count,
            'scope': scope,
            'json_size': os.path.getsize(ast_json) if os.path.exists(ast_json) else 0
        }
    
    def run_fan_in(self, signal_path: str) -> Dict[str, Any]:
        """
        分析信号的 fan-in（扇入）
        
        Args:
            signal_path: 信号路径，如 'top.cpu.alu.result'
        
        Returns:
            dict: fan-in 分析结果
        """
        cmd = [SLANG_BIN]
        cmd.extend(['--std', self.std])
        for inc_dir in self.include_dirs:
            cmd.extend(['-I', inc_dir])
        if self.top:
            cmd.extend(['--top', self.top])
        cmd.extend(['--fan-in', signal_path])
        cmd.extend(self.files)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return {
            'signal': signal_path,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    def run_fan_out(self, signal_path: str) -> Dict[str, Any]:
        """
        分析信号的 fan-out（扇出）
        
        Args:
            signal_path: 信号路径
        
        Returns:
            dict: fan-out 分析结果
        """
        cmd = [SLANG_BIN]
        cmd.extend(['--std', self.std])
        for inc_dir in self.include_dirs:
            cmd.extend(['-I', inc_dir])
        if self.top:
            cmd.extend(['--top', self.top])
        cmd.extend(['--fan-out', signal_path])
        cmd.extend(self.files)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        return {
            'signal': signal_path,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }
    
    @staticmethod
    def check_available() -> bool:
        """检查 slang 是否可用"""
        return os.path.isfile(SLANG_BIN) and os.access(SLANG_BIN, os.X_OK)
    
    @staticmethod
    def get_version() -> Optional[str]:
        """获取 slang 版本"""
        try:
            result = subprocess.run([SLANG_BIN, '--version'], 
                                   capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None


if __name__ == '__main__':
    print(f'Slang available: {SlangDriver.check_available()}')
    print(f'Slang version: {SlangDriver.get_version()}')
    
    # 测试运行
    test_file = os.path.expanduser('~/my_dv_proj/chipsonar/slang_test/design.sv')
    if os.path.exists(test_file):
        driver = SlangDriver([test_file], source_info=True)
        result = driver.run()
        print(f'\nSuccess: {result["success"]}')
        print(f'AST JSON: {result["ast_json"]}')
        print(f'Errors: {result["error_count"]}, Warnings: {result["warning_count"]}')
        
        # 测试 fan-in
        print('\n--- Fan-in test ---')
        fan_in = driver.run_fan_in('top.cnt_inst.count')
        print(fan_in['stdout'][:500] if fan_in['success'] else fan_in['stderr'][:500])