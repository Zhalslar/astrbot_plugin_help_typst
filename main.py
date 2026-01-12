import asyncio
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.message.components import Image

from .core import (
    BaseAnalyzer,
    CommandAnalyzer,
    EventAnalyzer,
    FilterAnalyzer,
    TypstRenderer,
)
from .domain import InternalCFG
from .utils import PluginConfig, TypstLayout


class HelpTypst(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 1. 配置 (字典 → 强类型的 Dataclass)
        self.config = PluginConfig.load(config)

        # 2. 路径
        self.plugin_dir = Path(__file__).parent
        self.data_dir = StarTools.get_data_dir()

        template_path = self.plugin_dir / "templates" / InternalCFG.NAME_TEMPLATE
        font_dir = self.plugin_dir / "resources" / InternalCFG.NAME_FONT_DIR

        # 3. 视图层
        self.prefixes: list[str] = self.context.get_config().get("wake_prefix", ["/"])

        self.layout = TypstLayout(self.config)

        # 4. 渲染引擎配置注入
        self.renderer = TypstRenderer(
            data_dir=self.data_dir,
            template_path=template_path,
            font_dir=font_dir,
            config=self.config,
        )

        # 5. 分析器
        self.cmd_analyzer = CommandAnalyzer(context, self.config)
        self.evt_analyzer = EventAnalyzer(context, self.config)
        self.flt_analyzer = FilterAnalyzer(context, self.config)

    async def initialize(self):
        pass

    async def terminate(self):
        """插件卸载时清理"""
        try:
            for f in self.data_dir.glob("temp_*"):
                try:
                    f.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    async def _handle_request(
        self,
        event: AstrMessageEvent,
        analyzer: BaseAnalyzer,
        title: str,
        mode: str,
        query: str | None,
    ):
        """通用请求处理逻辑"""

        def data_pipeline(save_path: Path) -> int:
            """数据流转"""
            # 数据层：获取对象
            plugins = analyzer.get_plugins(query)
            if not plugins:
                return 0

            # 视图层：决定标题 & 计算布局 & 写入JSON
            display_title = f'搜索结果: "{query}"' if query else title
            self.layout.dump_layout_json(
                plugins=plugins,
                save_path=save_path,
                title=display_title,
                mode=mode,
                prefixes=self.prefixes,
            )

            return len(plugins)

        result, error = await self.renderer.render(data_pipeline, mode, query)
        if error:
            yield event.plain_result(error)
            return
        if not result:
            return

        try:
            comps = [Image.fromFileSystem(p) for p in result.images]
            yield event.chain_result(comps)  # type: ignore
        finally:
            if result.temp_files:
                asyncio.create_task(self._cleanup_task(result.temp_files))


    async def _cleanup_task(self, files: list[Path]):
        """异步清理任务"""
        await asyncio.sleep(InternalCFG.DELAY_SEND)
        for p in files:
            try:
                if p.exists():
                    p.unlink()
            except Exception as e:
                logger.warning(f"[HelpTypst] 临时文件清理失败 {p}: {e}")

    @filter.command("helps", alias={"帮助", "菜单"})
    async def show_menu(self, event: AstrMessageEvent, query: str | None = None):
        """显示指令菜单"""
        if self.config.send_hint:
            yield event.plain_result("正在生成帮助图...")
        async for r in self._handle_request(
            event,
            analyzer=self.cmd_analyzer,
            title="AstrBot 指令菜单",
            mode="command",
            query=query,
        ):
            yield r

    @filter.command("events")
    async def show_events(self, event: AstrMessageEvent, query: str | None = None):
        """显示事件监听列表"""
        if self.config.send_hint:
            yield event.plain_result("正在分析事件监听器...")
        async for r in self._handle_request(
            event,
            analyzer=self.evt_analyzer,
            title="AstrBot 事件监听",
            mode="event",
            query=query,
        ):
            yield r

    @filter.command("filters")
    async def show_filters(self, event: AstrMessageEvent, query: str | None = None):
        """显示过滤器详情"""
        if self.config.send_hint:
            yield event.plain_result("正在分析过滤器...")
        async for r in self._handle_request(
            event,
            analyzer=self.flt_analyzer,
            title="AstrBot 过滤器分析",
            mode="filter",
            query=query,
        ):
            yield r
