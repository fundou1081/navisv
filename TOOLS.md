# TOOLS.md - Local Notes

## navisv 项目环境

### Python 环境

**项目基础环境**：`navisv/.venv`（Python 3.11 + networkx）
- 用于 navisv 项目的日常开发
- 激活：`source navisv/.venv/bin/activate`

**slang-netlist 环境**：`/usr/bin/python3`（Python 3.9.6，系统自带）
- **这是运行 slang-netlist 绑定的唯一可用 Python 3.9**
- 路径：`/Users/fundou/my_dv_proj/slang-netlist/install/`
- 直接 import，无需额外配置

### 验证 slang-netlist 可用

```bash
/usr/bin/python3 -c "
import sys
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install')
sys.path.insert(0, '/Users/fundou/my_dv_proj/slang-netlist/install/lib')
import pyslang_netlist as nl
from pyslang import driver as sl_driver

RTL_FILE = '/Users/fundou/my_dv_proj/opentitan/hw/ip/i2c/rtl/i2c_core.sv'
d = sl_driver.Driver()
d.addStandardArgs()
d.sourceLoader.addFiles(RTL_FILE)
ok = d.parseAllSources()
comp = d.createCompilation()
mgr = d.runAnalysis(comp)
graph = nl.NetlistGraph()
graph.build(comp, mgr)
print(f'Graph: {graph.num_nodes()} nodes, {graph.num_edges()} edges')
# Expected: Graph: 53 nodes, 56 edges
"
```

### slang-netlist 安装路径
- 安装目录：`~/my_dv_proj/slang-netlist/install`
- Python 绑定：
  - `~/my_dv_proj/slang-netlist/install/`（含 `__init__.py`）
  - `~/my_dv_proj/slang-netlist/install/lib/`（含 `.so` 文件）

### 运行 navisv slang-netlist 代码

所有调用 slang-netlist 的脚本必须使用 `/usr/bin/python3`：
```bash
/usr/bin/python3 my_script.py
```

或者在脚本开头添加 shebang：
```python
#!/usr/bin/env python3
```

### 已有可运行示例
- `~/my_skills/pyslang-netlist-examples/examples/` - 18 个可运行的 slang-netlist 示例
- `utils.py` 提供 `build_graph(sv_file)` 函数
- 运行示例：`/usr/bin/python3 examples/03_path_finder.py`

### OpenTitan I2C 模块（用于原型验证）
- 路径：`~/my_dv_proj/opentitan/hw/ip/i2c/rtl/`
- 核心文件：`i2c_core.sv`
- 验证：53 nodes, 56 edges