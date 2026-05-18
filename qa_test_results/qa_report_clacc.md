# OpenChip QA 测试结果

**日期**: 2026-05-18 17:38
**工具**: navisv

---

## 测试汇总

| 设计 | 文件数 | 节点 | 边 | 实例 | 未实例化 | 状态 |
|------|---------|------|-----|-------|----------|------|
| clacc | 16 | 687 | 275 | 79 | 4 | ✅ PASS |

---

## 详细结果

**顶层文件**: `/Users/fundou/my_dv_proj/clacc/bs_mult.v`

### 节点统计

- 总节点数: 687
- Port: 397
- State: 211
- Instance: 79

### 实例详情

- 已实例化: 75
- 未实例化: 4

**未实例化模块（可能缺少依赖文件）**:
- `pe.dual_clock_fifo`
- `pe.ifmap_spad`
- `pe.psum_spad`
- `pe.filt_spad`

### 边详情

- slang_get_drivers: 275

### API 测试

- **get_drivers**: ✅ 成功 (1)
- **get_loads**: ✅ 成功 (0)
- **find_path**: ✅ 成功 (4)
