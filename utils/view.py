import json
import math
from pathlib import Path
from typing import Any

from ..domain import PluginMetadata, RenderNode
from . import PluginConfig


class TypstLayout:
    """负责将结构化数据转换为 Typst 渲染所需的布局 JSON"""

    def __init__(self, config: PluginConfig):
        self.cfg = config

    def dump_layout_json(
        self,
        plugins: list[PluginMetadata],
        save_path: Path,
        title: str,
        mode: str,
        prefixes: list[str],
    ):
        """生成布局数据并写入文件"""
        payload = self._generate_balanced_payload(plugins, title, mode, prefixes)

        save_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _generate_balanced_payload(
        self, plugins: list[PluginMetadata], title: str, mode: str, prefixes: list[str]
    ) -> dict[str, Any]:
        """瀑布流分发逻辑"""
        giants = []
        complex_plugins = []
        single_node_plugins = []

        # 辅助函数：获取节点列表
        def get_nodes(p: PluginMetadata) -> list[RenderNode]:
            if hasattr(p, "nodes") and p.nodes:
                return p.nodes
            if hasattr(p, "command_nodes") and p.command_nodes: # type: ignore
                return p.command_nodes # type: ignore
            return []

        extract_singles = mode == "command"

        # 1. 预分类
        for p in plugins:
            nodes = get_nodes(p)

            # A: 工具调用 -> Singles
            is_tool = len(nodes) > 0 and (
                nodes[0].tag == "tool" or nodes[0].tag == "mcp"
            )
            if is_tool:
                single_node_plugins.append(p.model_dump())
                continue

            # B: 单指令 -> Singles (Command 模式)
            if extract_singles and len(nodes) == 1 and not nodes[0].is_group:
                single_node_plugins.append(p.model_dump())
                continue

            # C: 巨型块 -> Giants (Event/Filter 模式)
            h_val = self._estimate_height(nodes)
            if (
                mode in ("event", "filter")
                and h_val > self.cfg.giant_threshold
            ):
                giants.append(p.model_dump())
                continue

            # D: 其余 -> 瀑布流
            complex_plugins.append(p)

        # 2. 瀑布流平衡算法
        # 计算高度权重 (+80 是对卡片头部和Padding的估算)
        plugins_with_height = [
            (p, self._estimate_height(get_nodes(p)) + 80) for p in complex_plugins
        ]
        # 降序排列 (贪心算法基础)
        sorted_plugins = sorted(plugins_with_height, key=lambda x: x[1], reverse=True)

        cols_data = [[] for _ in range(3)]
        col_heights = [0] * 3

        for plugin, height in sorted_plugins:
            # 放入当前高度最小的列
            idx = col_heights.index(min(col_heights))
            cols_data[idx].append(plugin.model_dump())
            col_heights[idx] += height

        return {
            "title": title,
            "mode": mode,
            "prefixes": prefixes,
            "plugin_count": len(plugins),
            "giants": giants,
            "columns": cols_data,
            "singles": single_node_plugins,
        }

    def _estimate_height(self, nodes: list[RenderNode]) -> int:
        """高度估算器(暂硬编码，等待完善模板逻辑)"""
        total_h = 0
        complex_nodes = [n for n in nodes if n.is_group or n.desc != ""]
        simple_nodes = [n for n in nodes if not n.is_group and n.desc == ""]

        # 复杂节点：垂直堆叠
        for node in complex_nodes:
            if node.is_group:
                total_h += 60 + self._estimate_height(node.children)
            else:
                total_h += 60

        # 简单节点：3列网格
        if simple_nodes:
            rows = math.ceil(len(simple_nodes) / 3)
            total_h += rows * 30 + 10

        return total_h
