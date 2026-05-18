# picorv32 - navisv 分析结果

> 用 navisv 分析设计，回答验证问题

---

## 分析结果

**状态**: ❌ **SIGSEGV** (解析崩溃)

---

## Issue-O: picorv32 解析崩溃

### 问题

picorv32.v 解析时发生 segmentation fault：

```bash
$ /usr/bin/python3 -c "
from navisv.graph import DesignGraph
g = DesignGraph(['/Users/fundou/my_dv_proj/picorv32/picorv32.v'])
"

Command aborted by signal SIGSEGV
```

### 原因

这是 **Issue-O** 记录的问题：
- picorv32 解析时崩溃
- 可能与设计规模或 slang-netlist 的某个边界条件有关

### 分析

| 指标 | 数值 |
|------|------|
| 文件 | picorv32.v |
| 大小 | ~5000 行 |
| 状态 | ❌ 解析失败 |

---

## 可能的解决方案

1. **调查 segfault 原因**：需要 GDB 调试或 valgrind
2. **简化设计**：尝试只分析部分模块
3. **更新 slang-netlist**：可能需要修复 C++ 代码

---

## navisv 分析总结

| 问题 | navisv 可回答 | 说明 |
|------|---------------|------|
| Q1-S: ... | ❌ | 解析崩溃 |
| Q2-S: ... | ❌ | 解析崩溃 |
| Q3-S: ... | ❌ | 解析崩溃 |

---

## Issue 记录

| Issue | 描述 | 来源 |
|-------|------|------|
| **Issue-O** | picorv32 解析崩溃（segfault） | picorv32 分析 |

---

**navisv 版本**: v0.9
**分析日期**: 2026-05-18
**状态**: ❌ FAIL - 解析崩溃