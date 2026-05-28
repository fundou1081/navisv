#!/usr/bin/env python3
"""
场景 5: 嵌套 if 条件 → true_condition → coverage

从 AST 直接提取嵌套 if 条件的所有 true_condition 路径，
并转写为 covergroup 代码。

用法:
    python3 examples/nested_conditions_coverage.py [sv_file] [signal]
"""

import sys
import os
import json
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SLANG = os.path.expanduser('~/my_dv_proj/slang/slang')
SV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nested_conditions.sv')


def extract_ast(sv_file):
    """提取 AST JSON"""
    with tempfile.TemporaryDirectory() as od:
        ast_path = os.path.join(od, 'ast.json')
        subprocess.run([SLANG, '--ast-json', ast_path, sv_file],
                      capture_output=True, timeout=30)
        with open(ast_path) as f:
            return json.load(f)


def ast_expr_to_str(node):
    """将 AST 表达式转为字符串"""
    if not node:
        return ''
    
    kind = node.get('kind', '')
    
    if kind == 'NamedValue':
        sym = node.get('symbol', '')
        if ' ' in sym:
            return sym.split(' ')[-1]
        return sym
    
    if kind == 'IntegerLiteral':
        return node.get('constant', str(node.get('value', '')))
    
    if kind == 'BinaryOp':
        left = ast_expr_to_str(node.get('left', {}))
        right = ast_expr_to_str(node.get('right', {}))
        op = node.get('op', '?')
        op_map = {
            'Equality': '==', 'Inequality': '!=',
            'LessThan': '<', 'LessThanEqual': '<=',
            'GreaterThan': '>', 'GreaterThanEqual': '>=',
            'LogicalAnd': '&&', 'LogicalOr': '||',
            'BinaryAnd': '&', 'BinaryOr': '|',
        }
        return f'{left} {op_map.get(op, op)} {right}'
    
    if kind == 'UnaryOp':
        operand = ast_expr_to_str(node.get('operand', {}))
        op = node.get('op', '')
        if op == 'LogicalNot':
            return f'!({operand})'
        return operand
    
    if kind == 'Conversion':
        return ast_expr_to_str(node.get('operand', {}))
    
    return f'<{kind}>'


def extract_condition(cond_node):
    """从 conditions 节点提取条件字符串"""
    expr = cond_node.get('expr', {})
    return ast_expr_to_str(expr)


def find_target_paths(ast, target_signal):
    """找到所有对目标信号的赋值及其完整条件路径"""
    results = []
    
    def walk(node, cond_stack):
        if isinstance(node, dict):
            kind = node.get('kind', '')
            
            if kind == 'ProceduralBlock':
                body = node.get('body', {})
                walk(body, [])
                return
            
            if kind == 'Conditional':
                # 提取条件
                conditions = node.get('conditions', [])
                cond_strs = [extract_condition(c) for c in conditions]
                cond_str = ' && '.join(cond_strs) if cond_strs else ''
                
                # if 分支
                if_true = node.get('ifTrue', {})
                walk(if_true, cond_stack + [cond_str])
                
                # else 分支
                if_false = node.get('ifFalse', {})
                if if_false:
                    neg_cond = f'!({cond_str})' if cond_str else ''
                    walk(if_false, cond_stack + [neg_cond])
                return
            
            if kind == 'Case':
                # 暂不处理 case
                return
            
            if kind == 'ExpressionStatement':
                expr = node.get('expr', {})
                if expr.get('kind') == 'Assignment':
                    left = expr.get('left', {})
                    sym = left.get('symbol', '')
                    if sym.endswith(target_signal) or f' {target_signal}' in sym:
                        right = expr.get('right', {})
                        value_str = ast_expr_to_str(right)
                        # 构建 true_condition
                        real_conds = [c for c in cond_stack if c]
                        tc = ' && '.join(real_conds) if real_conds else 'always'
                        results.append({
                            'condition': tc,
                            'value': value_str,
                        })
                        return
            
            # 递归遍历
            for v in node.values():
                walk(v, cond_stack)
        
        elif isinstance(node, list):
            for item in node:
                walk(item, cond_stack)
    
    walk(ast, [])
    return results


def simplify_conditions(results):
    """简化和去重条件 (用 AST 遍历代替正则)"""
    seen = set()
    unique = []
    for r in results:
        cond = r['condition']
        # 多轮简化双重否定
        for _ in range(5):
            old = cond
            # !(!(x)) → x  (手动解析，不用正则)
            while True:
                idx = cond.find('!(!(')
                if idx < 0:
                    break
                # 找到匹配的 ))
                depth = 0
                start = idx + 4
                end = start
                for i in range(start, len(cond)):
                    if cond[i] == '(':
                        depth += 1
                    elif cond[i] == ')':
                        if depth == 0:
                            end = i
                            break
                        depth -= 1
                inner = cond[start:end]
                # 确认后面是 ))
                if cond[end:end+2] == '))':
                    cond = cond[:idx] + inner + cond[end+2:]
            if cond == old:
                break
        r = dict(r, condition=cond)
        key = (cond, r['value'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def parse_condition_signals(cond_str):
    """从条件字符串中提取信号名"""
    signals = []
    # 简单的词法分析
    tokens = cond_str.replace('(', ' ').replace(')', ' ').replace('!', ' ').replace('&&', ' ').replace('||', ' ').replace('==', ' ').replace('!=', ' ').replace('>', ' ').replace('<', ' ').split()
    for t in tokens:
        t = t.strip()
        if not t:
            continue
        # 跳过数字和常量
        try:
            int(t)
            continue
        except ValueError:
            pass
        if t.startswith('2') or t.startswith('3') or t.startswith('8'):
            continue
        if t in ('True', 'False', 'always'):
            continue
        if t not in signals:
            signals.append(t)
    return signals


def generate_coverage(results, signal_name):
    """生成 covergroup 代码"""
    lines = []
    lines.append(f'// 自动生成: {signal_name} 的 true_condition 覆盖')
    lines.append(f'// 条件路径数: {len(results)}')
    lines.append(f'')
    lines.append(f'covergroup cg_{signal_name}_conditions @(posedge clk);')
    
    # 收集所有条件信号
    all_cond_signals = set()
    for r in results:
        signals = parse_condition_signals(r['condition'])
        all_cond_signals.update(signals)
    
    # 为每个条件信号生成 coverpoint
    for sig in sorted(all_cond_signals):
        lines.append(f'')
        lines.append(f'    // 条件信号: {sig}')
        lines.append(f'    cp_{sig}: coverpoint {sig};')
    
    # 为每个路径生成注释和交叉覆盖
    for i, r in enumerate(results):
        cond = r['condition']
        value = r['value']
        
        lines.append(f'')
        lines.append(f'    // 路径 {i+1}: {signal_name} = {value}')
        lines.append(f'    // true_condition: {cond}')
    
    # 生成交叉覆盖
    if len(all_cond_signals) >= 2:
        cp_names = [f'cp_{s}' for s in sorted(all_cond_signals)]
        lines.append(f'')
        lines.append(f'    // 交叉覆盖')
        lines.append(f'    cx_all: cross {", ".join(cp_names[:4])};')
    
    lines.append(f'endgroup')
    return lines


def main():
    sv_file = sys.argv[1] if len(sys.argv) > 1 else SV_FILE
    target_signal = sys.argv[2] if len(sys.argv) > 2 else 'data_out'
    
    print('=' * 70)
    print(f'嵌套条件分析: {target_signal}')
    print('=' * 70)
    
    # 提取 AST
    print(f'\n提取 AST...')
    ast = extract_ast(sv_file)
    
    # 找到所有赋值和条件
    print(f'分析嵌套条件...')
    results = find_target_paths(ast, target_signal)
    
    # 简化
    results = simplify_conditions(results)
    
    print(f'\n找到 {len(results)} 个条件路径:\n')
    
    for i, r in enumerate(results):
        print(f'  路径 {i+1}:')
        print(f'    条件: {r["condition"]}')
        print(f'    赋值: {target_signal} = {r["value"]}')
        signals = parse_condition_signals(r['condition'])
        if signals:
            print(f'    信号: {", ".join(signals)}')
        print()
    
    # 生成 coverage
    print('=' * 70)
    print('生成 Covergroup 代码')
    print('=' * 70)
    print()
    
    cov_lines = generate_coverage(results, target_signal)
    code = '\n'.join(cov_lines)
    print(code)
    
    # 保存
    out_file = sv_file.replace('.sv', f'_{target_signal}_conditions.sv')
    with open(out_file, 'w') as f:
        f.write(code)
    print(f'\n已保存到: {out_file}')


if __name__ == '__main__':
    main()
