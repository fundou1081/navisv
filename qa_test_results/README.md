# qa_test_results - OpenChip QA 测试结果

## 用法

```bash
cd ~/my_dv_proj/navisv/qa_test_results

# 测试 serv_decode（单文件）
/usr/bin/python3 run_qa.py /Users/fundou/my_dv_proj/serv/rtl/serv_decode.v

# 测试 bs_mult（多文件）
/usr/bin/python3 run_qa.py /Users/fundou/my_dv_proj/clacc/bs_mult.v /Users/fundou/my_dv_proj/clacc/*.v

# 测试 darkriscv（多文件）
/usr/bin/python3 run_qa.py /Users/fundou/my_dv_proj/darkriscv/rtl/darkriscv.v /Users/fundou/my_dv_proj/darkriscv/rtl/*.v
```

## 测试报告

- `qa_report_serv.md` - serv_decode 测试结果
- `qa_report_clacc.md` - clacc 测试结果
- `qa_report_darkriscv.md` - darkriscv 测试结果

## 测试内容

1. **节点统计**: Port, State, Instance 数量
2. **实例详情**: 已实例化 vs 未实例化（缺少依赖文件）
3. **边详情**: 边来源（slang_get_drivers / pathfinder）
4. **API 测试**: get_drivers, get_loads, find_path

## 手动指定文件的重要性

navisv 需要完整的文件集合才能正确分析设计：

✅ 正确：
```bash
/usr/bin/python3 run_qa.py top.sv sub1.sv sub2.sv
```

❌ 错误（缺少依赖）：
```bash
/usr/bin/python3 run_qa.py top.sv  # sub1.sv, sub2.sv 未包含
```