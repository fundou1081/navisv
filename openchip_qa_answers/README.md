# OpenChip QA Answers - navisv 分析结果

## 目录

| 项目 | 模块 | 状态 |
|------|------|------|
| serv | serv_alu | ✅ 已完成 |
| serv | serv_decode | 🔄 待分析 |
| serv | serv_top | ⏳ 待分析 |
| clacc | bs_mult | ⏳ 待分析 |
| darkriscv | darkriscv | ⏳ 待分析 |
| ... | ... | ⏳ |

## 回答流程

1. 读取 `~/openchip-qa/*/verification/*/VERIFICATION_QUESTIONS.md`
2. 用 navisv 分析设计
3. 将答案写入 `openchip_qa_answers/[模块]_answers.md`

## 分析结果摘要

### serv_alu (2026-05-18)

- 节点数: 17
- 边数: 9
- 问题数: 7 个
- 已回答: 5 个
- 无法回答: 2 个 (parameter 提取、内部 wire 信号)

### 关键限制

1. **Parameter 提取** - navisv 不直接支持
2. **内部 wire 信号** - 未作为节点出现
3. **表达式语义** - 需要理解 Verilog 语义

---

## Issue 收集

| Issue | 描述 | 来源 |
|-------|------|------|
| **R-5** | parameter 值无法提取 | Q1-S |
| **R-6** | 内部 Net 信号（result_add, result_slt）未作为节点 | Q9-F |

---

**更新日期**: 2026-05-18