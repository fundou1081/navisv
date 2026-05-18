# OpenChip QA 测试结果 v2 (PathFinder 版本)

> 测试日期：2026-05-18
> 测试工具：navisv v0.8 + PathFinder
> 测试项目：按 openchip-qa 顺序

---

## 测试结果汇总

| 设计 | 节点数 | 边数 | 边来源 | 状态 |
|------|--------|------|--------|------|
| serv_alu | 24 | 9 | pathfinder=9 | ✅ |
| serv_decode | 101 | 3 | pathfinder=3 | ⚠️ |
| darkriscv | 76 | 0 | - | ❌ |
| clacc_bs_mult | 11 | 0 | - | ❌ |

---

## 分析

### serv_alu (✅ 正常)
- PathFinder 找到 9 条边
- 所有边都是 Input Port → Output Port
- 与预期一致

### serv_decode (⚠️ 边数减少)
- 之前 BFS: 17 条边
- 现在 PathFinder: 3 条边
- 需要调查为什么边数减少

### darkriscv (❌ 无边)
- 76 个节点，0 条边
- 可能原因：没有 Output Port 或路径查找失败

### clacc_bs_mult (❌ 无边)
- 11 个节点，0 条边
- 可能原因：所有端口都是 Input

---

## 边详情

### serv_alu
```
serv_alu.clk -> serv_alu.o_rd
serv_alu.i_buf -> serv_alu.o_rd
serv_alu.i_cmp_eq -> serv_alu.o_cmp
serv_alu.i_cmp_eq -> serv_alu.o_rd
serv_alu.i_cnt0 -> serv_alu.o_rd
serv_alu.i_en -> serv_alu.o_rd
serv_alu.i_rd_sel -> serv_alu.o_rd
serv_alu.i_rs1 -> serv_alu.o_rd
serv_alu.i_sub -> serv_alu.o_rd
```

### serv_decode (3 条边)
待补充

---

## 下一步
1. 调查 serv_decode 边数减少原因
2. 调查 darkriscv 无边的原因
3. 继续测试其他项目