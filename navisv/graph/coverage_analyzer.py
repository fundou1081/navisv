"""
CoverageAnalyzer - 条件覆盖率分析

从 DesignGraph 提取的覆盖率分析逻辑:
- get_condition_coverage: 信号条件覆盖率
- analyze_condition_coverage: 批量条件覆盖率分析
"""

from typing import Dict, List, Any, Optional


class CoverageAnalyzer:
    """条件覆盖率分析"""

    def __init__(self, graph):
        """
        Args:
            graph: DesignGraph 实例
        """
        self.graph = graph

    def get_condition_coverage(self, signal: str) -> Dict[str, Any]:
        """
        获取信号的条件覆盖率分析

        Args:
            signal: 信号路径

        Returns:
            {
                'signal': signal,
                'total_conditions': int,
                'conditions': [
                    {
                        'kind': 'if'|'case'|'plain'|'ternary',
                        'condition': str,
                        'statement': str,
                        'location': str,
                        'is_redundant': bool,
                        'redundancy_reason': str or None
                    }
                ],
                'coverage_summary': {
                    'if_count': int,
                    'case_count': int,
                    'plain_count': int,
                    'ternary_count': int,
                    'redundant_count': int
                },
                'warnings': [str]  # 可能的死代码或问题
            }
        """
        result = {
            'signal': signal,
            'total_conditions': 0,
            'conditions': [],
            'coverage_summary': {
                'if_count': 0,
                'case_count': 0,
                'plain_count': 0,
                'ternary_count': 0,
                'redundant_count': 0
            },
            'warnings': []
        }

        condition_key = self.graph._find_condition_key(signal)
        if not condition_key:
            result['warnings'].append(f"Signal '{signal}' has no conditions")
            return result

        conds = self.graph._DesignGraph__signal_conditions[condition_key]
        result['total_conditions'] = len(conds)

        # 统计条件类型
        kind_counts = {'if': 0, 'case': 0, 'plain': 0, 'ternary': 0}
        seen_conditions = {}  # 用于检测冗余

        for c in conds:
            kind = c.get('kind', 'unknown')
            condition = c.get('condition', '')
            statement = c.get('statement', '')
            location = c.get('location', {})

            # 统计
            if kind in kind_counts:
                kind_counts[kind] += 1

            # 检测冗余
            is_redundant = False
            redundancy_reason = None

            # 检查是否有相同的 condition + statement
            key = (condition, statement)
            if key in seen_conditions:
                is_redundant = True
                redundancy_reason = f"Duplicate condition-statement pair (first at index {seen_conditions[key]})"
            else:
                seen_conditions[key] = len(result['conditions'])

            # 检查是否有互斥的条件对
            if condition and 'else' not in condition.lower():
                negated = f"!{condition}" if not condition.startswith('!') else condition[1:]
                for i, existing in enumerate(result['conditions']):
                    if existing['condition'] == negated and existing['kind'] == kind:
                        # 这是一个 if/else 对，不是冗余
                        pass

            # 构建 location 字符串
            loc_str = ''
            if location:
                file_name = location.get('file', '')
                if '/' in file_name:
                    file_name = file_name.split('/')[-1]
                line = location.get('line', 0)
                col = location.get('column', 0)
                loc_str = f"{file_name}:{line}:{col}"

            cond_entry = {
                'kind': kind,
                'condition': condition,
                'statement': statement,
                'location': loc_str,
                'is_redundant': is_redundant,
                'redundancy_reason': redundancy_reason
            }
            result['conditions'].append(cond_entry)

            if is_redundant:
                kind_counts['redundant_count'] = kind_counts.get('redundant_count', 0) + 1

        result['coverage_summary'] = kind_counts

        # 分析警告
        if kind_counts['if'] > 5:
            result['warnings'].append("Signal has many if conditions, may need simplification")

        if kind_counts['case'] == 1 and kind_counts['plain'] > 2:
            result['warnings'].append("Single case condition with many plain assignments may indicate unmodeled states")

        # 检查是否有死代码风险
        # 如果有多个互斥的条件组合，可能有路径未被覆盖
        case_conditions = [c['condition'] for c in conds if c.get('kind') == 'case']
        if case_conditions:
            # 检查是否有 default case
            has_default = any('default' in c.get('statement', '').lower() for c in conds)
            if not has_default and len(case_conditions) < 5:
                result['warnings'].append("Case statement without explicit default may have unreachable states")

        return result

    def analyze_condition_coverage(self, signals: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        批量分析多个信号的条件覆盖率

        Args:
            signals: 信号列表, None 表示分析所有有条件的信号

        Returns:
            {
                'total_signals': int,
                'total_conditions': int,
                'signals_with_redundancy': int,
                'dead_code_signals': [str],
                'results': {signal: get_condition_coverage(signal)}
            }
        """
        if signals is None:
            signals = [s for s, c in self.graph._DesignGraph__signal_conditions.items() if c]

        results = {}
        signals_with_redundancy = 0
        dead_code_signals = []
        total_conditions = 0

        for sig in signals:
            coverage = self.get_condition_coverage(sig)
            results[sig] = coverage

            total_conditions += coverage['total_conditions']

            # 检查冗余
            has_redundant = any(c.get('is_redundant', False) for c in coverage['conditions'])
            if has_redundant:
                signals_with_redundancy += 1

            # 检查死代码风险
            for warning in coverage['warnings']:
                if 'default' in warning or 'unreachable' in warning:
                    dead_code_signals.append(sig)
                    break

        return {
            'total_signals': len(signals),
            'total_conditions': total_conditions,
            'signals_with_redundancy': signals_with_redundancy,
            'dead_code_signals': dead_code_signals,
            'results': results
        }

