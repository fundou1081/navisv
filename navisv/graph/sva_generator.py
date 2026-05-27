"""
sva_generator.py - 从 DesignGraph 生成 SVA (SystemVerilog Assertions)

从图的信号关系、true_condition、constraint 信息生成可直接用于 formal/sim 的 SVA property。

生成策略:
  1. 有 true_condition 的边 → assert conditional path
  2. 有 constraint 的变量 → assert range
  3. 信号驱动关系 → assert implication
"""

from typing import List, Dict, Any, Optional
import re


class SVAGenerator:
    """
    从 DesignGraph 生成 SVA
    
    Usage:
        gen = SVAGenerator(design_graph)
        sva_text = gen.generate()           # 完整 SVA 文本
        props = gen.generate_properties()    # 结构化 property 列表
    """
    
    def __init__(self, dg, constraint_graph=None, covergroup_analyzer=None):
        self.dg = dg
        self.cg = constraint_graph
        self.cga = covergroup_analyzer
    
    def generate(self) -> str:
        """生成完整 SVA 文本"""
        props = self.generate_properties()
        lines = []
        for prop in props:
            lines.append(prop['declaration'])
            lines.append(prop['body'])
            lines.append(prop['assertion'])
            lines.append('')
        return '\n'.join(lines)
    
    def generate_properties(self) -> List[Dict[str, str]]:
        """生成结构化 property 列表"""
        props = []
        seen = set()
        
        # 策略 1: 从 true_condition 生成
        props.extend(self._gen_from_true_conditions(seen))
        
        # 策略 2: 从 constraint 生成
        if self.cg:
            props.extend(self._gen_from_constraints(seen))
        
        return props
    
    def _gen_from_true_conditions(self, seen: set) -> List[Dict[str, str]]:
        """从图边的 true_condition 生成 property"""
        props = []

        for src, dst, data in self.dg.graph.edges(data=True):
            tc = data.get('true_condition', '')
            if not tc:
                continue

            # 跳过时钟/复位边
            ek = data.get('edge_kind', '')
            if ek in ('PosEdge', 'NegEdge'):
                continue

            src_name = src.split('.')[-1]
            dst_name = dst.split('.')[-1]

            # 多条件用 | 分隔, 拆成独立 property
            conditions = [c.strip() for c in tc.split('|') if c.strip()]

            for cond in conditions:
                if cond in seen:
                    continue
                seen.add(cond)

                sva_expr, disable = self._tc_to_sva(cond)
                if not sva_expr:
                    continue

                prop_name = f'p_{dst_name}_{src_name}_{len(props)}'
                prop_name = re.sub(r'[^a-zA-Z0-9_]', '_', prop_name)

                disable_str = f' disable iff ({disable})' if disable else ''
                declaration = f'  property {prop_name};'
                body = f'    @(posedge clk){disable_str} {sva_expr} |-> ({dst_name} == {src_name});'
                assertion = f'  endproperty\n  assert property ({prop_name});'

                props.append({
                    'name': prop_name,
                    'declaration': declaration,
                    'body': body,
                    'assertion': assertion,
                    'source': f'true_condition: {cond}',
                    'signals': [src_name, dst_name],
                })

        return props
    
    def _gen_from_constraints(self, seen: set) -> List[Dict[str, str]]:
        """从 ConstraintGraph 生成 range assertion"""
        props = []
        
        for cls in self.cg.get_classes():
            for var in self.cg.get_variables_in_class(cls['full_path']):
                var_path = var['full_path']
                var_name = var['name']
                
                # 检查是否有 inside 约束
                cons = self.cg.get_constraints_for_variable(var_path)
                for c in cons:
                    body = c.get('constraint_body', '')
                    inside_match = re.search(r'inside\s*\{([^}]+)\}', body)
                    if not inside_match:
                        continue
                    
                    range_str = inside_match.group(1).strip()
                    key = f'{var_name}:{range_str}'
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    prop_name = f'p_{var_name}_range'
                    prop_name = re.sub(r'[^a-zA-Z0-9_]', '_', prop_name)
                    
                    declaration = f'  property {prop_name};'
                    body_str = f'    @(posedge clk) {var_name} inside {{ {range_str} }};'
                    assertion = f'  endproperty\n  assert property ({prop_name});'
                    
                    props.append({
                        'name': prop_name,
                        'declaration': declaration,
                        'body': body_str,
                        'assertion': assertion,
                        'source': 'constraint: ' + c['constraint_name'],
                        'signals': [var_name],
                    })
        
        return props
    
    def _tc_to_sva(self, tc: str) -> tuple:
        """
        将 true_condition 字符串转换为 SVA 表达式和 disable 条件

        Returns: (sva_expr, disable_condition)
        """
        if not tc:
            return '', ''

        # 多条件用 | 分隔 (多个边合并), 取第一个有效条件
        # 清理 !!rst_n 等双重否定
        tc_clean = tc.replace('!!', '')

        # 分离 reset 条件
        disable = ''
        parts = tc_clean.split(' && ')
        sva_parts = []

        for part in parts:
            part = part.strip()
            if not part:
                continue
            # rst_n / !rst_n → disable iff
            if part in ('rst_n',) or part == '!rst_n':
                disable = 'rst_n' if part == 'rst_n' else part[1:]
            elif part.startswith('!') and not part.startswith('!='):
                # 其他否定条件作为前提
                sva_parts.append(part)
            else:
                sva_parts.append(part)

        sva_expr = ' && '.join(sva_parts) if sva_parts else '1'
        return sva_expr, disable
