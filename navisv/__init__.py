# navisv - Semantic navigation middleware for AI debugging agents
# navisv 架构 v0.9 (JSON-based)

"""
navisv: 基于 slang + slang-netlist JSON 输出的语义导航中间件

三层架构：
1. Drivers: SlangDriver, NetlistDriver (调用原生工具)
2. Parsers: ASTParser, NetlistParser (解析 JSON)
3. Graph: GraphBuilder, DesignGraph (构建图)

使用示例：
    #!/usr/bin/env python3
    
    from navisv import DesignDriver
    
    # 方式1: 直接构建
    driver = DesignDriver(['design.sv'])
    driver.build()
    dg = driver.design_graph
    
    # 方式2: 便捷函数
    from navisv import from_files
    dg = from_files(['design.sv'])
    
    # 查询
    print(dg.get_registers())
    print(dg.get_fanin_cone('top.cpu.alu.result'))
"""

__version__ = "0.9.0"

from navisv.drivers import SlangDriver, NetlistDriver, DesignDriver, from_files
from navisv.graph import DesignGraph

__all__ = [
    'SlangDriver',
    'NetlistDriver',
    'DesignDriver',
    'from_files',
    'DesignGraph',
]