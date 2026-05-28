# 场景 5: 嵌套条件 → true_condition → Coverage

## 问题

一个信号受到多层嵌套 `if` 条件控制：
```systemverilog
always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        data_out <= 0;
    else if (en)
        if (mode == 0)
            if (!err_flag)
                if (priority > 3)
                    data_out <= data_in + 1;
                else
                    data_out <= data_in;
            else
                data_out <= 8'hFE;
        else if (mode == 1)
            ...
end
```

需要：
1. 提取所有到达 `data_out` 的条件路径
2. 生成完整的 true_condition 表达式
3. 转写为 covergroup

## 解决方案

navisv 从 AST 直接遍历嵌套条件树，提取每条赋值路径的完整条件链。

## 运行

```bash
cd ~/my_dv_proj/navisv

# 分析 data_out 的条件路径
python3 examples/nested_conditions_coverage.py

# 分析其他信号
python3 examples/nested_conditions_coverage.py examples/nested_conditions.sv data_out
```

## 输出示例

```
找到 10 个条件路径:

  路径 1:
    条件: !(rst_n)
    赋值: data_out = 8'd0          ← 复位路径

  路径 2:
    条件: rst_n && en && mode == 2'b0 && !(err_flag) && priority_level > 3'b11
    赋值: data_out = data_in + 1   ← 正常路径 (高优先级)

  路径 4:
    条件: rst_n && en && mode == 2'b0 && err_flag
    赋值: data_out = 8'd254        ← 错误路径

  路径 10:
    条件: rst_n && !(en)
    赋值: data_out = 8'd0          ← 未使能路径
```

## 生成的 Covergroup

```systemverilog
covergroup cg_data_out_conditions @(posedge clk);
    // 条件信号 coverpoint
    cp_en:             coverpoint en;
    cp_err_flag:       coverpoint err_flag;
    cp_mode:           coverpoint mode;
    cp_priority_level: coverpoint priority_level;
    cp_rst_n:          coverpoint rst_n;

    // 交叉覆盖: 所有条件信号的组合
    cx_all: cross cp_en, cp_err_flag, cp_mode, cp_priority_level;
endgroup
```

## 技术细节

### 条件简化

自动简化双重否定：
```
!(!(rst_n))  →  rst_n
!(!(err_flag))  →  err_flag
```

### 条件链构建

遍历 AST 的 Conditional 节点：
```
Conditional (rst_n)
  ├─ ifTrue:  路径条件 += !(rst_n)
  └─ ifFalse: 路径条件 += rst_n
      └─ Conditional (en)
          ├─ ifTrue:  路径条件 += en
          └─ ifFalse: 路径条件 += !(en)
              └─ Conditional (mode == 0)
                  ...
```

每到达一个 `data_out` 赋值，记录完整的条件链。

## 应用场景

1. **覆盖率驱动验证**: 为每个条件路径生成 coverpoint，确保仿真覆盖所有分支
2. **死代码检测**: 如果某条路径的条件永远为假（如 `mode == 2'b0 && mode == 2'b1`），说明有死代码
3. **条件组合爆炸分析**: 了解条件组合数量，评估验证复杂度
