# navisv Debug 实战：RTL 信号异常排查

本文档介绍如何用 navisv 快速定位 RTL 信号异常的根因。

## 典型 Debug 场景

```
仿真报错: pipeline_data 的值不符合预期
    ↓
需要回答:
  1. 谁影响 pipeline_data? (向后追踪)
  2. pipeline_data 影响谁? (向前追踪)
  3. 什么条件下信号变化? (条件分析)
  4. 涉及哪些模块端口? (端口映射)
```

## 使用方法

```bash
# 调试默认信号
python3 examples/debug_signal.py

# 调试指定信号
python3 examples/debug_signal.py debug_demo.mux_out

# 调试多个信号
python3 examples/debug_signal.py debug_demo.pipeline_data debug_demo.flag
```

## 输出解读

### 1. 基本属性

```
📋 基本属性:
  路径:     debug_demo.pipeline_data
  类型:     State          ← 寄存器/线网
  位宽:     [0:7]          ← 8位宽
  模块:     debug_demo     ← 所属模块
  位置:     line 18        ← 源码位置
  时序:     sequential     ← 时序逻辑
```

### 2. 向后追踪 (谁影响它?)

```
⬅️  向后追踪：谁影响这个信号？

  直接驱动 (4):
    ← debug_demo.clk      [Port]    ← 时钟
    ← debug_demo.en       [Port]    ← 使能
    ← debug_demo.mux_out  [Net]     ← 数据来源
    ← debug_demo.rst_n    [Port]    ← 复位

  Fan-in cone (7 个上游信号):
    [debug_demo]
    📌 clk        [Port In]    ← 模块输入端口
    📌 data_a     [Port In]    ← 模块输入端口
    📌 data_b     [Port In]    ← 模块输入端口
    📌 en         [Port In]    ← 模块输入端口
    📌 rst_n      [Port In]    ← 模块输入端口
    📌 sel        [Port In]    ← 模块输入端口
       mux_out    [Net]        ← 内部信号
```

**关键信息：**
- `📌` 标记的是模块端口（可直接在波形中查看）
- 路径显示信号的传递链：`data_a → mux_out → pipeline_data`

### 3. 向前追踪 (它影响谁?)

```
➡️  向前追踪：这个信号影响谁？

  直接负载 (2):
    → debug_demo.flag      [State]   ← 标志位
    → debug_demo.processed [Net]     ← 处理后的数据

  Fan-out cone (3 个下游信号):
    flag       [State]
    processed  [Net]
    result     [State]

  📌 此信号影响的模块端口:
    → debug_demo.result    ← 输出端口
      路径 (4 跳):
        pipeline_data → processed → result → result
    → debug_demo.flag      ← 输出端口
      路径 (3 跳):
        pipeline_data → flag → flag
```

### 4. 条件分析

```
📊 条件分析：什么条件下信号变化？

  条件 (2):
    • rst_n  [if]     ← 复位时清零
    • en     [if]     ← 使能时更新
```

### 5. Debug 建议

```
💡 Debug 建议

  1. 检查输入端口值:
     • debug_demo.clk        ← 检查时钟是否正常
     • debug_demo.rst_n      ← 检查复位是否释放
     • debug_demo.data_a     ← 检查数据源
     • debug_demo.data_b     ← 检查数据源
     • debug_demo.sel        ← 检查选择信号
     • debug_demo.en         ← 检查使能信号

  2. 检查直接驱动信号值:
     • debug_demo.mux_out    ← 检查 MUX 输出

  3. 检查条件信号值:
     • debug_demo.rst_n      ← 复位是否有效?
     • debug_demo.en         ← 使能是否有效?

  4. 受影响的输出:
     • debug_demo.result     ← 输出是否正确
     • debug_demo.flag       ← 标志位是否正确

  5. 相关寄存器 (检查时钟和复位):
     • debug_demo.pipeline_data
```

## 实际 Debug 流程

### 场景: pipeline_data 值异常

```
1. 运行 debug_signal.py，查看输出
   → 发现 pipeline_data 由 mux_out 驱动
   → mux_out 由 sel 选择 data_a 或 data_b

2. 检查波形:
   - sel 的值是什么?
   - data_a / data_b 的值是什么?
   - mux_out 的值是否正确?

3. 如果 mux_out 正确:
   - 检查 en 信号: 是否在应该更新时为 0?
   - 检查 rst_n: 是否意外复位?

4. 如果 mux_out 不正确:
   - 检查 sel: 选择信号是否正确?
   - 检查 data_a / data_b: 数据源是否正确?

5. 追踪到输出:
   - pipeline_data → processed → result
   - 检查 processed 的值是否正确
   - 检查 result 的值是否正确
```

## 进阶用法

### 比较两个信号

```bash
python3 examples/debug_signal.py debug_demo.mux_out debug_demo.processed
```

### 用于回归测试

在 CI 中自动运行 debug 分析，生成信号依赖报告：

```bash
python3 examples/debug_signal.py > debug_report.txt
```

### 集成到波形查看器

将 navisv 的输出导入 GTKWave 或其他波形查看器，自动高亮相关信号。
