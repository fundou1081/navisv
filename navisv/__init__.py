# navisv - Semantic navigation middleware for AI debugging agents
# navisv 架构 v0.8

"""
navisv: 基于 slang-netlist 的语义导航中间件

层次：
- Graph Layer: DesignGraph（networkx DiGraph 唯一存储）
- Query Layer: QueryService（原子查询）
- App Layer: SignalProfileApp 等场景应用

使用示例：
    #!/usr/bin/env python3
    # 必须使用 /usr/bin/python3（Python 3.9）运行
    
    from navisv.graph import DesignGraph
    from navisv.query import QueryService
    from navisv.apps import SignalProfileApp

    # 构建图
    graph = DesignGraph(["path/to/design.sv"])
    
    # 原子查询
    query = QueryService(graph)
    drivers = query.get_drivers("top.clk")
    
    # 场景 App
    app = SignalProfileApp(query)
    result = app.run("top.clk")
    print(result.summary)
"""

__version__ = "0.1.0"

from navisv.graph import DesignGraph, DriverInfo, LoadInfo
from navisv.query import QueryService
from navisv.apps import AppResponse, SignalProfileApp

__all__ = [
    'DesignGraph',
    'DriverInfo',
    'LoadInfo',
    'QueryService',
    'AppResponse',
    'SignalProfileApp',
]