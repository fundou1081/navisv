# slang-netlist 时序逻辑追踪 - 重要发现

## 日期
2026-05-18

## 核心发现

### PathFinder 可以追踪时序逻辑，但有限制

slang-netlist 的 `PathFinder.find()` 确实可以追踪通过 State 节点的时序逻辑路径，但**前提是每个信号只能有一个 always block**。

### 导致追踪失败的模式

```verilog
// 当同一信号在两个 always block 中赋值时，PathFinder 追踪失败
always @(posedge clk)
  b = a;           // combinational style =
always_ff @(posedge clk or posedge rst)
  b <= a;          // sequential style <=
```

验证测试：
| 测试用例 | pathExists(a→b) |
|----------|-----------------|
| only always_ff | ✅ 可达 |
| always + always_ff (同一信号) | ❌ 不可达 |
| always + always_ff + wire | ❌ 不可达 |
| always_ff with wire | ✅ 可达 |

### serv_decode.v 正是这种模式

```verilog
// line 277: combinational style =
o_alu_sub = co_alu_sub;

// line 338: sequential style <=
o_alu_sub <= co_alu_sub;
```

这就是为什么 PathFinder 找不到 o_alu_sub 的路径。

### State 节点的作用

- 当 always_ff 或非阻塞赋值 (`<=`) 存在时，NetlistBuilder 创建 **State 节点**
- State 节点代表时序逻辑的状态存储
- PathFinder.find() 可以穿过 State 节点（不是 CombEdgePredicate 过滤的对象）

### 相关文件

- `/Users/fundou/my_dv_proj/slang-netlist/tests/unit/SequentialStateTests.cpp` - 时序逻辑测试
- `/Users/fundou/my_dv_proj/slang-netlist/tests/unit/PathTests.cpp` - 路径测试
- `/Users/fundou/my_dv_proj/navisv/SEQUENTIAL_LOGIC_DEEP_INVESTIGATION.md` - 详细分析

## 结论

slang-netlist 的设计限制导致它无法处理一个信号在多个 always block 中赋值的情况。

可能的解决方案：
1. 简化 design，避免一个信号在多个 always block 中赋值
2. 使用其他工具进行时序逻辑分析
3. 修改 slang-netlist 源码以支持这种模式