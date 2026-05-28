"""
DesignDriver - 完整的 DesignGraph 构建器

组合 SlangDriver + NetlistDriver + GraphBuilder + DesignGraph
提供统一的用户接口
"""

import os
import tempfile
from typing import List, Optional, Dict, Any

from navisv.drivers import SlangDriver, NetlistDriver
from navisv.parsers import ASTParser, NetlistParser, ConstraintParser, CovergroupParser, SVAParser, CallGraphParser
from navisv.graph import GraphBuilder, DesignGraph, ConstraintGraph, CovergroupAnalyzer, SVAGenerator, CallGraph


class DesignDriver:
    """
    完整的 DesignGraph 构建器
    
    用户只需要:
        driver = DesignDriver(['design.sv'])
        dg = driver.build()
        print(dg.get_registers())
    
    内部流程:
        1. SlangDriver 生成 ast.json
        2. NetlistDriver 生成 netlist.json
        3. ASTParser 解析 ast.json
        4. NetlistParser 解析 netlist.json
        5. GraphBuilder 构建 MultiDiGraph
        6. 返回 DesignGraph
    """
    
    def __init__(
        self,
        files: List[str],
        top: Optional[str] = None,
        include_dirs: Optional[List[str]] = None,
        defines: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        output_dir: Optional[str] = None,
        std: str = '1800-2017',
    ):
        """
        Args:
            files: 设计文件列表
            top: 顶层模块名
            include_dirs: include 搜索路径
            defines: 宏定义
            params: 参数覆盖
            output_dir: 输出目录（默认使用临时目录）
            std: 语言标准
        """
        self.files = files
        self.top = top
        self.include_dirs = include_dirs or []
        self.defines = defines or {}
        self.params = params or {}
        self.output_dir = output_dir or tempfile.mkdtemp(prefix='navisv_')
        self.std = std
        
        # 结果缓存
        self._slang_driver: Optional[SlangDriver] = None
        self._netlist_driver: Optional[NetlistDriver] = None
        self._netlist_result: Optional[Dict] = None  # NetlistDriver.run() 结果
        self._ast_parser: Optional[ASTParser] = None
        self._netlist_parser: Optional[NetlistParser] = None
        self._graph_builder: Optional[GraphBuilder] = None
        self._design_graph: Optional[DesignGraph] = None
        
        # ConstraintGraph 缓存
        self._constraint_parser: Optional[ConstraintParser] = None
        self._constraint_graph: Optional[ConstraintGraph] = None
        
        # CovergroupAnalyzer 缓存
        self._covergroup_parser: Optional[CovergroupParser] = None
        self._covergroup_analyzer: Optional[CovergroupAnalyzer] = None
        
        # SVA 缓存
        self._sva_parser: Optional[SVAParser] = None
        
        # CallGraph 缓存
        self._call_graph_parser: Optional[CallGraphParser] = None
        self._call_graph: Optional[CallGraph] = None
        
        # 诊断信息
        self._diagnostics: List[Dict[str, Any]] = []
        self._error_count: int = 0
        self._warning_count: int = 0
    
    def check_tools(self) -> Dict[str, bool]:
        """检查工具是否可用"""
        return {
            'slang': SlangDriver.check_available(),
            'slang-netlist': NetlistDriver.check_available(),
        }
    
    def build(self) -> 'DesignDriver':
        """
        构建 DesignGraph
        
        Returns:
            self (链式调用)
        """
        # 1. 生成 AST JSON
        self._run_slang()
        
        # 2. 生成 Netlist JSON
        self._run_netlist()
        
        # 3. 解析 JSON
        self._parse_jsons()
        
        # 4. 构建图
        self._build_graph()
        
        return self
    
    def _run_slang(self):
        """运行 slang 生成 AST"""
        self._slang_driver = SlangDriver(
            files=self.files,
            output_dir=self.output_dir,
            std=self.std,
            include_dirs=self.include_dirs,
            defines=self.defines,
            top=self.top,
            source_info=True,
        )
        result = self._slang_driver.run()
        
        if result['diagnostics']:
            self._diagnostics = result['diagnostics']
        self._error_count = result['error_count']
        self._warning_count = result['warning_count']
    
    def _run_netlist(self):
        """运行 slang-netlist 生成 Netlist"""
        self._netlist_driver = NetlistDriver(
            files=self.files,
            output_dir=self.output_dir,
            std=self.std,
            include_dirs=self.include_dirs,
            defines=self.defines,
            top=self.top,
        )
        self._netlist_result = self._netlist_driver.run()
    
    def _parse_jsons(self):
        """解析 JSON 文件"""
        # AST
        ast_json = os.path.join(self.output_dir, 'ast.json')
        if os.path.exists(ast_json):
            self._ast_parser = ASTParser(ast_json).parse()
        else:
            self._ast_parser = None
            ast_json = None
        
        # 保存 ast_json 路径供 GraphBuilder 使用
        self._ast_json_path = ast_json if os.path.exists(ast_json) else None
        # 源文件列表（用于读取源码）
        self._source_files = self.files
        
        # Netlist
        netlist_json = os.path.join(self.output_dir, 'netlist.json')
        if os.path.exists(netlist_json):
            self._netlist_parser = NetlistParser(netlist_json).parse()
        else:
            self._netlist_parser = None
    
    def _build_graph(self):
        """构建 Graph"""
        if not self._ast_parser or not self._netlist_parser:
            # 即使解析失败也创建空图
            import networkx as nx
            self._design_graph = DesignGraph(nx.MultiDiGraph())
            return
        
        self._graph_builder = GraphBuilder(self._ast_parser, self._netlist_parser, 
                                               self._ast_json_path, self._source_files)
        graph = self._graph_builder.build()
        self._design_graph = DesignGraph(graph, self._graph_builder._signal_conditions, self._netlist_driver)
        
        # 构建 ConstraintGraph
        self._build_constraint_graph()
        
        # 构建 CovergroupAnalyzer
        self._build_covergroup_analyzer()
        
        # 构建 SVAParser
        self._build_sva_parser()
        
        # 构建 CallGraph
        self._build_call_graph()
    
    def _build_constraint_graph(self):
        """构建 ConstraintGraph"""
        ast_json = os.path.join(self.output_dir, 'ast.json')
        if os.path.exists(ast_json):
            try:
                self._constraint_parser = ConstraintParser(ast_json, self._source_files)
                self._constraint_parser.parse()
                self._constraint_graph = ConstraintGraph(self._constraint_parser)
            except Exception as e:
                import logging
                logging.getLogger('navisv').warning(f'ConstraintGraph 构建失败: {e}')
                self._constraint_graph = None
    
    def _build_covergroup_analyzer(self):
        """构建 CovergroupAnalyzer"""
        ast_json = os.path.join(self.output_dir, 'ast.json')
        if os.path.exists(ast_json):
            try:
                self._covergroup_parser = CovergroupParser(ast_json)
                self._covergroup_parser.parse()
                self._covergroup_analyzer = CovergroupAnalyzer(
                    self._covergroup_parser, self._constraint_graph
                )
            except Exception as e:
                import logging
                logging.getLogger('navisv').warning(f'CovergroupAnalyzer 构建失败: {e}')
                self._covergroup_analyzer = None
    
    def _build_sva_parser(self):
        """构建 SVAParser"""
        ast_json = os.path.join(self.output_dir, 'ast.json')
        if os.path.exists(ast_json):
            try:
                self._sva_parser = SVAParser(ast_json)
                self._sva_parser.parse()
            except Exception as e:
                import logging
                logging.getLogger('navisv').warning(f'SVAParser 构建失败: {e}')
                self._sva_parser = None
    
    def _build_call_graph(self):
        """构建 CallGraph"""
        ast_json = os.path.join(self.output_dir, 'ast.json')
        if os.path.exists(ast_json):
            try:
                self._call_graph_parser = CallGraphParser(ast_json)
                self._call_graph_parser.parse()
                self._call_graph = CallGraph(self._call_graph_parser)
            except Exception as e:
                import logging
                logging.getLogger('navisv').warning(f'CallGraph 构建失败: {e}')
                self._call_graph = None
    
    @property
    def design_graph(self) -> DesignGraph:
        """获取 DesignGraph"""
        if self._design_graph is None:
            self.build()
        return self._design_graph
    
    @property
    def constraint_graph(self) -> Optional[ConstraintGraph]:
        """获取 ConstraintGraph"""
        if self._constraint_graph is None and self._constraint_parser is None:
            self.build()
        return self._constraint_graph
    
    @property
    def covergroups(self) -> Optional[CovergroupAnalyzer]:
        """获取 CovergroupAnalyzer"""
        if self._covergroup_analyzer is None and self._covergroup_parser is None:
            self.build()
        return self._covergroup_analyzer
    
    @property
    def sva_generator(self) -> Optional[SVAGenerator]:
        """获取 SVAGenerator"""
        if self._design_graph is None:
            self.build()
        return SVAGenerator(self._design_graph, self._constraint_graph, self._covergroup_analyzer)
    
    @property
    def sva(self) -> Optional[SVAParser]:
        """获取 SVAParser (SVA 原始数据)"""
        if self._sva_parser is None:
            self.build()
        return self._sva_parser
    
    @property
    def call_graph(self) -> Optional[CallGraph]:
        """获取 CallGraph"""
        if self._call_graph is None and self._call_graph_parser is None:
            self.build()
        return self._call_graph
    
    @property
    def graph(self):
        """直接获取 networkx MultiDiGraph"""
        return self.design_graph.graph
    
    @property
    def diagnostics(self) -> List[Dict[str, Any]]:
        """获取诊断信息"""
        return self._diagnostics
    
    @property
    def error_count(self) -> int:
        """错误数量"""
        return self._error_count
    
    @property
    def warning_count(self) -> int:
        """警告数量"""
        return self._warning_count
    
    @property
    def success(self) -> bool:
        """是否成功（无错误）"""
        return self._error_count == 0
    
    def summary(self) -> Dict[str, Any]:
        """获取摘要"""
        return {
            'files': self.files,
            'output_dir': self.output_dir,
            'success': self.success,
            'error_count': self._error_count,
            'warning_count': self._warning_count,
            'slang_ast': os.path.exists(os.path.join(self.output_dir, 'ast.json')),
            'netlist_json': os.path.exists(os.path.join(self.output_dir, 'netlist.json')),
            'graph': self.design_graph.summary() if self._design_graph else {},
        }
    
    def __repr__(self) -> str:
        if self._design_graph:
            return f"DesignDriver({self.design_graph})"
        return f"DesignDriver(files={len(self.files)})"


def from_files(
    files: List[str],
    top: Optional[str] = None,
    include_dirs: Optional[List[str]] = None,
    **kwargs
) -> DesignGraph:
    """
    便捷函数：从文件列表创建 DesignGraph
    
    Args:
        files: 文件列表
        top: 顶层模块
        include_dirs: include 目录
        **kwargs: 其他参数
    
    Returns:
        DesignGraph
    """
    driver = DesignDriver(files, top=top, include_dirs=include_dirs, **kwargs)
    return driver.build().design_graph


if __name__ == '__main__':
    # 测试
    test_file = '/Users/fundou/my_dv_proj/chipsonar/slang_test/design.sv'
    
    print("=== DesignDriver 测试 ===")
    
    # 检查工具
    driver = DesignDriver([test_file])
    tools = driver.check_tools()
    print(f"Tools: {tools}")
    
    # 构建
    driver.build()
    
    print(f"\nSuccess: {driver.success}")
    print(f"Errors: {driver.error_count}")
    print(f"Warnings: {driver.warning_count}")
    print(f"\nSummary: {driver.summary()}")
    
    print(f"\nDesignGraph: {driver.design_graph}")
    print(f"Registers: {driver.design_graph.get_registers()}")
    print(f"Fan-in cone of 'top.cnt_inst.count': {driver.design_graph.get_fanin_cone('top.cnt_inst.count')}")