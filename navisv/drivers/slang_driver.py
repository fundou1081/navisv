"""
slang driver - 调用 slang 工具生成 AST JSON

主要功能：
- 语法检查
- 生成 AST JSON
- 生成诊断 JSON
- 依赖文件生成
"""

import logging
import subprocess
import os
import json
import tempfile
from typing import List, Optional, Dict, Any


# slang 工具路径
from navisv.config import SLANG_BIN


logger = logging.getLogger(__name__)


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
                 scope: Optional[str] = None,
                 single_unit: bool = False):
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
            single_unit: 是否将所有文件视为同一编译单元
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
        self.single_unit = single_unit
    
    def _build_cmd(self) -> List[str]:
        """构建命令"""
        cmd = [SLANG_BIN]
        
        # 语言标准
        cmd.extend(['--std', self.std])
        
        # 单元模式
        if self.single_unit:
            cmd.append('--single-unit')
        
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
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to parse diagnostics JSON: {e}")
                diagnostics = []
                error_count = -1
                warning_count = -1
        
        json_size = os.path.getsize(ast_json) if os.path.exists(ast_json) else 0
        
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
            'json_size': json_size,
            'parse_error': None if error_count >= 0 else "Failed to parse diagnostics"
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
    
    @staticmethod
    def compile_check(files: Optional[List[str]] = None,
                      include_dirs: Optional[List[str]] = None,
                      defines: Optional[Dict[str, str]] = None,
                      std: str = '1800-2017',
                      top: Optional[str] = None,
                      ignore_unknown_modules: bool = False,
                      include_dirs_extra: Optional[List[str]] = None,
                      filelist: Optional[str] = None,
                      filelist_includes: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        快速检查源码编译状态（语法检查）

        使用 slang 的 lint-only 模式，不生成完整 AST，只检查编译错误。

        Args:
            files: 源文件列表
            include_dirs: include 目录列表
            defines: 宏定义
            std: 语言标准 (默认 1800-2017)
            top: 顶层模块名
            ignore_unknown_modules: 是否忽略未知模块
            include_dirs_extra: 额外的 include 目录
            filelist: filelist 文件路径（自动使用 -F 选项）
            filelist_includes: filelist 内的相对 include 目录

        Returns:
            dict: {
                'success': bool,          # 是否通过编译检查
                'returncode': int,        # 返回码
                'error_count': int,      # 错误数
                'warning_count': int,     # 警告数
                'diagnostics': list,      # 诊断信息列表
                'errors': list,           # 错误详情 (file, line, column, message)
                'warnings': list,         # 警告详情
                'stdout': str,
                'stderr': str,
            }
        """
        import json as json_module
        
        # 合并 include 目录
        all_include_dirs = list(include_dirs or [])
        if include_dirs_extra:
            all_include_dirs.extend(include_dirs_extra)
        
        # 处理 filelist
        cmd_files = list(files) if files else []
        
        if filelist:
            # 使用 slang -F 选项加载 filelist
            # filelist 中的相对路径基于 filelist 文件所在目录
            if filelist_includes:
                # 动态添加 filelist 所在目录为 include 目录
                filelist_dir = os.path.dirname(os.path.abspath(filelist))
                all_include_dirs.append(filelist_dir)
            
            # -F 选项会自动解析 filelist 内的 +incdir 和 -I 选项
            cmd_files.append(f'-F')
            cmd_files.append(filelist)
        
        # P0-2: 多文件时自动生成临时 filelist
        elif len(cmd_files) > 1:
            # 自动生成临时 filelist，调用 slang -F
            with tempfile.TemporaryDirectory(prefix='navisv_filelist_') as fl_dir:
                # 创建 filelist，按文件名排序保证确定性
                fl_path = os.path.join(fl_dir, 'auto_filelist.f')
                with open(fl_path, 'w') as fl:
                    for f in sorted(cmd_files):
                        fl.write(f + '\n')
                
                # 使用 filelist 调用
                cmd_files = []
                cmd_files.append(f'-F')
                cmd_files.append(fl_path)
        
        with tempfile.TemporaryDirectory(prefix='navisv_compile_check_') as tmp_dir:
            diag_json = os.path.join(tmp_dir, 'diag.json')
            
            cmd = [SLANG_BIN]
            
            # 语言标准
            cmd.extend(['--std', std])
            
            # Include 路径
            for inc_dir in all_include_dirs:
                cmd.extend(['-I', inc_dir])
            
            # 宏定义
            for macro, value in (defines or {}).items():
                if value:
                    cmd.extend(['-D', f'{macro}={value}'])
                else:
                    cmd.extend(['-D', macro])
            
            # 顶层模块
            if top:
                cmd.extend(['--top', top])
            
            # 忽略未知模块
            if ignore_unknown_modules:
                cmd.append('--ignore-unknown-modules')
            
            # 只做 lint，不生成 AST
            cmd.append('--lint-only')
            
            # 诊断输出到文件
            cmd.extend(['--diag-json', diag_json])
            
            # 源文件
            cmd.extend(cmd_files)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            # 解析诊断
            diagnostics = []
            errors = []
            warnings = []
            error_count = 0
            warning_count = 0
            
            if os.path.exists(diag_json):
                try:
                    with open(diag_json) as f:
                        diag_data = json_module.load(f)
                        diagnostics = diag_data if isinstance(diag_data, list) else [diag_data]
                        
                    for d in diagnostics:
                        entry = {
                            'severity': d.get('severity', 'Unknown'),
                            'message': d.get('message', ''),
                            'code': d.get('code', ''),
                        }
                        
                        # 提取位置信息 - slang 使用 "location" 格式: "file:line:column"
                        if 'location' in d:
                            loc_str = d['location']
                            if ':' in loc_str:
                                parts = loc_str.rsplit(':', 2)
                                if len(parts) == 3:
                                    entry['file'] = parts[0]
                                    entry['line'] = int(parts[1]) if parts[1].isdigit() else 0
                                    entry['column'] = int(parts[2]) if parts[2].isdigit() else 0
                                elif len(parts) == 2:
                                    entry['file'] = parts[0]
                                    entry['line'] = int(parts[1]) if parts[1].isdigit() else 0
                        
                        severity_lower = d.get('severity', '').lower()
                        if severity_lower == 'error':
                            error_count += 1
                            errors.append(entry)
                        elif severity_lower == 'warning':
                            warning_count += 1
                            warnings.append(entry)
                except (json_module.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to parse diagnostics JSON: {e}")
                    diagnostics = []
                    errors = [{'message': f'Parse error: {e}', 'severity': 'Error', 'file': '', 'line': 0}]
                    warnings_list = []
                    error_count = 1
            
            return {
                'success': error_count == 0,
                'returncode': result.returncode,
                'error_count': error_count,
                'warning_count': warning_count,
                'diagnostics': diagnostics,
                'errors': errors,
                'warnings': warnings,
                'stdout': result.stdout,
                'stderr': result.stderr,
            }


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