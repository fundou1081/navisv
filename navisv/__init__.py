# navisv - Semantic navigation middleware for AI debugging agents
# navisv 架构 v0.9 (JSON-based)

"""
navisv: 基于 slang + slang-netlist JSON 输出的语义导航中间件

层次：
- Drivers Layer: SlangDriver, NetlistDriver（调用原生工具）
- Parsers Layer: ASTParser, NetlistParser（解析 JSON）
- Graph Layer: DesignGraph（networkx DiGraph 唯一存储）

使用示例：
    #!/usr/bin/env python3
    
    from navisv.drivers import SlangDriver, NetlistDriver

    # 驱动 slang 生成 AST
    slang = SlangDriver(['design.sv'])
    ast_result = slang.run()
    
    # 驱动 slang-netlist 生成 netlist
    netlist_driver = NetlistDriver(['design.sv'])
    netlist_result = netlist_driver.run()
"""

__version__ = "0.9.0"

__all__ = []