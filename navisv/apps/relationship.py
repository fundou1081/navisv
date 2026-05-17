# apps/relationship.py - 信号关系分析 App
# navisv 架构 v0.8 - App Layer

"""
RelationshipApp: "这两个信号之间是什么关系？"

场景：分析两个信号之间的关系：
- 是否有驱动关系（直接路径）
- 是否有共同驱动源
- 是否有共同负载
- 是否符合握手协议模式（valid/ready、req/ack）

铁律约束：
- [铁律17] App 是唯一生成 summary 的层
- [铁律13] App 通过 QueryService 获取数据，不直接访问 DesignGraph
"""

import re
from .base import BaseApp, AppResponse


# 常见握手协议命名模式
HANDSHAKE_PATTERNS = [
    (r'valid', r'ready'),
    (r'req', r'ack'),
    (r'req', r'grant'),
    (r'set', r'ack'),
    (r'vld', r'rdy'),
]


class RelationshipApp(BaseApp):
    """
    信号关系分析：两个信号之间是什么关系。
    
    输入：两个信号路径
    输出：关系类型 + 共同源/负载 + 路径 + 协议推断
    """

    def run(self, signal_a: str, signal_b: str) -> AppResponse:
        """
        分析两个信号之间的关系。
        
        Args:
            signal_a: 信号 A
            signal_b: 信号 B
            
        Returns:
            AppResponse: structured + summary + confidence
        """
        # 检查信号是否存在
        exists_a = self._check_signal_exists(signal_a)
        exists_b = self._check_signal_exists(signal_b)

        if not exists_a or not exists_b:
            missing = []
            if not exists_a:
                missing.append(signal_a)
            if not exists_b:
                missing.append(signal_b)
            return AppResponse(
                structured={"signal_a": signal_a, "signal_b": signal_b,
                           "error": f"signal_not_found: {', '.join(missing)}"},
                summary=f"信号 {', '.join(missing)} 不存在",
                confidence="uncertain",
                experimental=False
            )

        # 1. 共同驱动源（两个信号被什么共同驱动）
        drivers_a = set(d.id for d in self.query.get_drivers(signal_a))
        drivers_b = set(d.id for d in self.query.get_drivers(signal_b))
        common_sources = drivers_a & drivers_b

        # 2. 共同负载（两个信号共同驱动什么）
        loads_a = set(l.id for l in self.query.get_loads(signal_a))
        loads_b = set(l.id for l in self.query.get_loads(signal_b))
        common_loads = loads_a & loads_b

        # 3. 路径查找（A → B 或 B → A）
        path_ab = self.query.find_path(signal_a, signal_b)
        path_ba = self.query.find_path(signal_b, signal_a)

        # 4. 判断关系类型
        if path_ab and len(path_ab) > 0:
            # A 驱动 B
            relation_type = "A_drives_B"
            path = path_ab
        elif path_ba and len(path_ba) > 0:
            # B 驱动 A
            relation_type = "B_drives_A"
            path = path_ba
        elif common_sources:
            relation_type = "common_sources"
            path = []
        elif common_loads:
            relation_type = "common_loads"
            path = []
        else:
            relation_type = "no_direct_relationship"
            path = []

        # 5. 协议模式检测
        inferred_protocol = self._detect_protocol(signal_a, signal_b)

        # 6. 节点属性
        name_a = self.query._graph.node_attr(signal_a).get('name', signal_a)
        name_b = self.query._graph.node_attr(signal_b).get('name', signal_b)

        # 构建 structured
        structured = {
            "signal_a": signal_a,
            "name_a": name_a,
            "signal_b": signal_b,
            "name_b": name_b,
            "relation_type": relation_type,
            "path": path,
            "common_sources": list(common_sources),
            "common_loads": list(common_loads),
            "inferred_protocol": inferred_protocol,
            "drivers_a": list(drivers_a),
            "drivers_b": list(drivers_b),
            "loads_a": list(loads_a),
            "loads_b": list(loads_b),
        }

        # 生成摘要
        summary_parts = []
        summary_parts.append(f"信号 {name_a} ↔ {name_b} 关系分析")

        if relation_type == "A_drives_B":
            summary_parts.append(f"{name_a} 驱动 {name_b}")
            if path and len(path) > 2:
                summary_parts.append(f"（路径长度 {len(path)} 步）")
        elif relation_type == "B_drives_A":
            summary_parts.append(f"{name_b} 驱动 {name_a}")
            if path and len(path) > 2:
                summary_parts.append(f"（路径长度 {len(path)} 步）")
        elif common_sources:
            if len(common_sources) == 1:
                summary_parts.append(f"共同被 {list(common_sources)[0]} 驱动")
            else:
                summary_parts.append(f"共同被 {len(common_sources)} 个信号驱动")
        elif common_loads:
            if len(common_loads) == 1:
                summary_parts.append(f"共同驱动 {list(common_loads)[0]}")
            else:
                summary_parts.append(f"共同驱动 {len(common_loads)} 个信号")
        else:
            summary_parts.append("无直接驱动关系")

        if inferred_protocol:
            summary_parts.append(f"[推断] 可能为 {inferred_protocol} 协议")

        summary = "，".join(summary_parts) + "。"

        # 置信度
        if common_sources or common_loads or path:
            confidence = "high"
        elif drivers_a or drivers_b:
            confidence = "medium"
        else:
            confidence = "uncertain"

        return AppResponse(
            structured=structured,
            summary=summary,
            confidence=confidence,
            experimental=False
        )

    def _detect_protocol(self, signal_a: str, signal_b: str) -> str:
        """检测是否符合握手协议模式"""
        name_a = self.query._graph.node_attr(signal_a).get('name', '').lower()
        name_b = self.query._graph.node_attr(signal_b).get('name', '').lower()

        for pattern_a, pattern_b in HANDSHAKE_PATTERNS:
            if (re.search(pattern_a, name_a) and re.search(pattern_b, name_b)) or \
               (re.search(pattern_a, name_b) and re.search(pattern_b, name_a)):
                # 找到匹配的模式名称
                for pname, (pa, pb) in zip(
                    ['valid/ready', 'req/ack', 'req/grant', 'set/ack', 'vld/rdy'],
                    HANDSHAKE_PATTERNS
                ):
                    if (re.search(pa, name_a) and re.search(pb, name_b)) or \
                       (re.search(pa, name_b) and re.search(pb, name_a)):
                        return pname
        return ""