# navisv 已知问题 & 路线图

## P0 - 必须解决

### 1. slang-netlist 拼接表达式不建模数据依赖
- **现象**: `assign {a, b, c} = {x, y, z}` 中 x→a 的路径丢失
- **根因**: slang-netlist 将拼接表达式视为整体，不拆分内部依赖
- **影响**: 涉及拼接赋值的信号路径追踪失败
- **方案**: 从 AST 解析拼接表达式，按位宽拆分后补建边 ✅ (已部分实现)

### 2. slang-netlist 中间节点无出边
- **现象**: `Conditional(452) → Assignment(454)` 是死端，无出边
- **根因**: slang-netlist 生成的 netlist 中，条件块内的赋值节点只有入边没有出边
- **影响**: always_ff 中 if/else 分支的赋值路径断开
- **方案**: 在 `_add_edges` 中递归穿透中间节点，连接源到最终目标 ✅ (已部分实现)

### 3. 路径追踪 2 个残留失败
- **uart_controller.s_apb_pwrite_i → reg_wr_en_o**: Conditional→Assignment 死端
- **uart_controller.uart_rx.uart_rx_i → rx_fifo_data_o**: data_rcvd 未连接
- **根因**: 上述 P0-1 和 P0-2 的组合效应
- **状态**: 待深入分析 netlist JSON 结构

## P1 - 重要

### 4. OpenTitan 编译失败
- **现象**: prim 依赖链太深，`prim_assert.sv` 等找不到
- **影响**: 无法分析真实大型项目
- **方案**: 支持 `--define` 宏定义 + 更智能的 include 路径发现

### 5. 接口跨模块连接未建模
- **现象**: `modport` 信息提取了，但接口信号的跨模块连接未建立
- **影响**: 通过接口连接的模块间路径追踪失败
- **方案**: 解析接口实例化 + modport 绑定，自动补建跨模块边

### 6. 多文件自动发现增强
- **现状**: 仅扫描同目录
- **增强**: 解析 `include` 指令 + 递归扫描子目录

## P2 - 优化

### 7. 增量构建
- **现状**: 每次 `build()` 从零解析
- **方案**: 文件哈希缓存，只重建变化的部分

### 8. 信号名模糊匹配
- **现状**: 信号名必须精确匹配
- **方案**: 支持 `*` 通配符 + 大小写不敏感

### 9. CoverGroup 未完善
- option 解析返回空 dict
- sample 事件返回 None
- 关联信号覆盖检查 (依赖 DesignGraph)

### 10. 接口支持增强
- Interface 内部信号不参与路径追踪
- 跨模块 interface 连接未建模

## P3 - 远期

### 11. CDC 完整分析
### 12. Enum/Struct 完整类型系统
### 13. CLI 交互式模式
### 14. 仿真集成 (波形查看器)
### 15. 代码生成 (从约束生成 SV)
