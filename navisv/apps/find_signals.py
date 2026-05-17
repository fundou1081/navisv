# apps/find_signals.py - 信号查找 App
# navisv 架构 v0.8 - App Layer

"""
FindSignalsApp: "我想找一个信号，在哪儿？"

场景：基于描述查找匹配的信号：
- 按名称正则匹配
- 按标签（tags）过滤
- 按模块过滤
- 关键字映射到 tags（时钟→clock，输入→port_input 等）

铁律约束：
- [铁律17] App 是唯一生成 summary 的层
- [铁律13] App 通过 QueryService 获取数据，不直接访问 DesignGraph
"""

import re
from .base import BaseApp, AppResponse


# 自然语言关键字 → tags 映射
KEYWORD_TAG_MAP = {
    '时钟': 'clock',
    'clock': 'clock',
    '复位': 'reset',
    'reset': 'reset',
    '输入': 'port_input',
    'input': 'port_input',
    '输出': 'port_output',
    'output': 'port_output',
    '寄存器': 'register',
    'register': 'register',
    '线': 'wire',
    'wire': 'wire',
}


class FindSignalsApp(BaseApp):
    """
    信号查找：按名称、标签、模块查找匹配的信号。
    
    输入：描述文本或命名模式
    输出：匹配信号列表 + 自然语言摘要
    """

    def run(self, description: str = "", name_pattern: str = "", tags: list = None,
            module: str = "", limit: int = 20) -> AppResponse:
        """
        查找匹配的信号。
        
        Args:
            description: 自然语言描述（如"时钟信号"、"输入端口"）
            name_pattern: 信号名称正则（可选，与 description 叠加）
            tags: 标签过滤列表（可选）
            module: 模块名过滤（可选）
            limit: 最大返回数量，默认 20
            
        Returns:
            AppResponse: structured + summary + confidence
        """
        tags = tags or []
        matched = set()

        # 1. 从 description 提取 tags
        if description:
            desc_lower = description.lower()
            for keyword, tag in KEYWORD_TAG_MAP.items():
                if keyword.lower() in desc_lower:
                    tags.append(tag)

            # 从 description 生成 name_pattern（如果未提供）
            # 简单规则：空格分隔的词作为通配符
            if not name_pattern:
                # 提取英文字符串作为模式
                words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', description)
                if words:
                    # 取第一个较长的词作为前缀模式
                    for w in sorted(words, key=len, reverse=True):
                        if len(w) >= 3:
                            name_pattern = f"{w}.*"
                            break

        # 2. 执行 search_signals
        results = self.query.search_signals(name_pattern=name_pattern, tags=tags)

        # 3. 模块过滤
        if module:
            results = [r for r in results
                       if self.query._graph.node_attr(r).get('module', '') == module]

        # 4. 限制数量
        total = len(results)
        truncated = results[:limit]
        truncated_set = set(truncated)

        # 5. 按模块分组
        by_module = {}
        for sig in truncated:
            mod = self.query._graph.node_attr(sig).get('module', 'unknown')
            if mod not in by_module:
                by_module[mod] = []
            by_module[mod].append(sig)

        # 6. 构建 structured
        structured = {
            "query": {
                "description": description,
                "name_pattern": name_pattern,
                "tags": tags,
                "module": module,
            },
            "total_found": total,
            "returned": len(truncated),
            "signals": [
                {
                    "id": sig,
                    "name": self.query._graph.node_attr(sig).get('name', ''),
                    "module": self.query._graph.node_attr(sig).get('module', ''),
                    "tags": list(self.query._graph.node_attr(sig).get('tags', set())),
                }
                for sig in truncated
            ],
            "by_module": {mod: list(sigs) for mod, sigs in by_module.items()},
        }

        # 7. 生成摘要
        summary_parts = []

        if description:
            summary_parts.append(f"查找 '{description}'")
        elif name_pattern:
            summary_parts.append(f"按模式 '{name_pattern}' 查找")
        else:
            summary_parts.append("查找信号")

        if tags:
            summary_parts.append(f"（标签：{', '.join(tags)}）")

        summary_parts.append(f"找到 {total} 个匹配")

        if total == 0:
            summary_parts.append("，无匹配结果")
        elif total > limit:
            summary_parts.append(f"，显示前 {limit} 个")
        elif total <= 5:
            # 少量结果，列出详细信息
            for sig in truncated:
                name = self.query._graph.node_attr(sig).get('name', sig)
                mod = self.query._graph.node_attr(sig).get('module', '')
                summary_parts.append(f"\n  - {name}（{mod}）")
        else:
            # 大量结果，按模块汇总
            summary_parts.append(f"，分布在 {len(by_module)} 个模块")

        summary = "".join(summary_parts)

        return AppResponse(
            structured=structured,
            summary=summary,
            confidence="high" if results else "uncertain",
            experimental=False
        )