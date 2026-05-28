# OpenTitan UART 分析示例

本示例展示如何用 navisv 分析 OpenTitan 的 UART IP 模块。

## 前置条件

1. 克隆 OpenTitan 仓库：
```bash
git clone https://github.com/lowRISC/opentitan.git ~/my_dv_proj/opentitan
```

2. 确保 navisv 已安装：
```bash
cd ~/my_dv_proj/navisv && pip install -e .
```

## 完整示例

```python
"""
OpenTitan UART 模块分析

展示 navisv 对真实大型 IP 的分析能力：
- 40 个依赖文件（包 + 宏 + 模块）
- 2290 个节点
- 路径追踪 + 寄存器查询 + 时序分析
"""

from navisv import DesignDriver
import tempfile
import os
import glob

# ============================================================
# 1. 配置 OpenTitan 路径
# ============================================================

OT_ROOT = os.path.expanduser('~/my_dv_proj/opentitan/hw/')

INCLUDE_DIRS = [
    OT_ROOT + 'ip/prim/rtl/',           # prim 基础库
    OT_ROOT + 'ip/prim_generic/rtl/',    # prim 通用实现
    OT_ROOT + 'ip/tlul/rtl/',           # TileLink UL 总线
    OT_ROOT + 'ip/uart/rtl/',           # UART 模块
    OT_ROOT + 'top_earlgrey/rtl/',      # 顶层 RTL
    OT_ROOT + 'top_earlgrey/rtl/autogen/',  # 自动生成的包
    OT_ROOT + 'vendor/lowrisc_ibex/rtl/',   # Ibex CPU 包
    OT_ROOT + 'ip/prim_xilinx/rtl/',    # Xilinx prim 实现
]

# ============================================================
# 2. 迭代式依赖收集
# ============================================================

def collect_opentitan_deps(top_file, include_dirs):
    """
    自动收集 OpenTitan 依赖文件
    
    OpenTitan 依赖链极深（40+ 文件），需要迭代式收集：
    每次编译→找缺失→添加→重编译，直到无错误。
    """
    # 建立文件名→路径索引
    file_index = {}
    for d in include_dirs:
        if os.path.isdir(d):
            for f in glob.glob(d + '*.sv'):
                base = os.path.basename(f).replace('.sv', '')
                file_index.setdefault(base, []).append(f)
    
    # 宏文件必须在最前面
    files = []
    if 'prim_flop_macros' in file_index:
        files.append(file_index['prim_flop_macros'][0])
    files.append(top_file)
    
    import re
    
    for iteration in range(20):
        with tempfile.TemporaryDirectory(prefix='navisv_') as od:
            dd = DesignDriver(files, output_dir=od, include_dirs=include_dirs)
            dd.build()
            errors = [d for d in dd._diagnostics if d['severity'] == 'error']
            
            if not errors:
                print(f"✅ 编译成功: {len(files)} 文件, 迭代 {iteration} 次")
                return files
            
            # 提取缺失的包/模块名
            missing = set()
            for d in errors:
                m = re.search(
                    r"unknown (?:class or package|module|macro) '(\w+)'",
                    d['message']
                )
                if m:
                    missing.add(m.group(1))
            
            # 查找并添加缺失文件
            added = []
            for name in missing:
                if name in file_index and file_index[name]:
                    path = file_index[name][0]
                    if path not in files:
                        files.insert(0, path)  # 包文件放前面
                        added.append(name)
            
            if not added:
                print(f"❌ 无法自动解决依赖: {missing}")
                break
            
            print(f"  迭代 {iteration}: 添加 {len(added)} 个: {', '.join(added)}")
    
    return files


# ============================================================
# 3. 构建 DesignGraph
# ============================================================

print("=" * 60)
print("OpenTitan UART 分析")
print("=" * 60)

# 自动收集依赖
uart_file = OT_ROOT + 'ip/uart/rtl/uart.sv'
files = collect_opentitan_deps(uart_file, INCLUDE_DIRS)

# 构建图
with tempfile.TemporaryDirectory(prefix='navisv_') as od:
    dd = DesignDriver(files, output_dir=od, include_dirs=INCLUDE_DIRS)
    dd.build()
    dg = dd.design_graph

    # ============================================================
    # 4. 基本统计
    # ============================================================
    
    print(f"\n📊 基本统计:")
    print(f"  节点: {len(dg.graph.nodes)}")
    print(f"  边:   {len(dg.graph.edges)}")
    print(f"  输入端口: {len(dg.get_input_ports())}")
    print(f"  输出端口: {len(dg.get_output_ports())}")
    print(f"  寄存器:   {len(dg.get_registers())}")

    # ============================================================
    # 5. 路径追踪
    # ============================================================
    
    print(f"\n🔍 路径追踪:")
    
    # UART RX 输入 → FIFO 数据输出
    r = dg.trace_full_path('uart.cio_rx_i', 'uart.uart_core.rx_fifo_data')
    print(f"  cio_rx_i → rx_fifo_data: status={r['status']} path={len(r['path'])} 跳")
    if r['path']:
        for p in r['path'][:3]:
            print(f"    {p['signal']}")
        print(f"    ...")
        for p in r['path'][-2:]:
            print(f"    {p['signal']}")

    # ============================================================
    # 6. 信号查询
    # ============================================================
    
    print(f"\n📡 信号查询:")
    
    # 查找 RX 相关信号
    rx_signals = dg.find_nodes('*rx*')
    print(f"  RX 相关信号: {len(rx_signals)} 个")
    for s in sorted(rx_signals)[:5]:
        print(f"    {s}")
    
    # 查找寄存器
    regs = dg.get_registers()
    print(f"\n  寄存器: {len(regs)} 个")
    for r in sorted(regs)[:5]:
        print(f"    {r}")

    # ============================================================
    # 7. 条件覆盖率
    # ============================================================
    
    print(f"\n📈 条件覆盖率:")
    coverage = dg.analyze_condition_coverage()
    print(f"  总信号: {coverage.get('total_signals', 0)}")
    print(f"  有条件信号: {coverage.get('signals_with_conditions', 0)}")

    # ============================================================
    # 8. 时序报告
    # ============================================================
    
    print(f"\n⏱️ 时序报告:")
    report = dg.generate_timing_report(format='text')
    if 'clock_domains' in report:
        for clk, info in list(report['clock_domains'].items())[:3]:
            print(f"  {clk}: {info.get('register_count', 0)} 寄存器")
```

## 运行结果

```
============================================================
OpenTitan UART 分析
============================================================
  迭代 0: 添加 5 个: tlul_pkg, uart_core, top_racl_pkg, prim_alert_pkg, uart_reg_top
  迭代 1: 添加 7 个: prim_subreg_pkg, uart_reg_pkg, tlul_adapter_reg, ...
  迭代 2: 添加 8 个: prim_buf, prim_subreg_ext, prim_util_pkg, ...
  迭代 3: 添加 11 个: prim_secded_inv_39_32_enc, prim_fifo_sync, ...
  迭代 4: 添加 4 个: prim_alert_sender, prim_intr_hw, ...
  迭代 5: 添加 3 个: prim_sec_anchor_flop, prim_sec_anchor_buf, prim_diff_decode
✅ 编译成功: 40 文件, 迭代 6 次

📊 基本统计:
  节点: 2290
  边:   4890
  输入端口: 696
  输出端口: 409
  寄存器:   112

🔍 路径追踪:
  cio_rx_i → rx_fifo_data: status=found path=15 跳
    uart.cio_rx_i
    uart.uart_core.rx
    uart.uart_core.uart_rx.idle_d
    ...
    uart.uart_core.rx_fifo_data
```

## 关键点

### 为什么需要 `single_unit` 模式？

OpenTitan 的依赖链极深：
```
uart.sv
  → uart_core.sv (需要 tlul_pkg, prim_alert_pkg)
    → tlul_adapter_reg.sv (需要 tlul_pkg, prim_subreg_pkg)
      → prim_subreg.sv (需要 prim_util_pkg)
        → prim_buf.sv (需要 prim_pkg)
          → prim_flop_macros.sv (宏定义)
```

slang 默认每个文件独立编译，无法解析跨文件的包引用。
`--single-unit` 将所有文件视为同一编译单元，自动解析依赖。

### 依赖收集策略

1. **宏文件优先**：`prim_flop_macros.sv` 必须在最前面
2. **包文件次之**：`*_pkg.sv` 在模块之前
3. **迭代收集**：每次编译后添加缺失的依赖，直到无错误

### 性能

| 阶段 | 耗时 |
|------|------|
| 依赖收集 (6 次迭代) | ~3 秒 |
| 最终编译 | ~0.5 秒 |
| 路径追踪 | ~20ms |
| 信号查询 | <1ms |
