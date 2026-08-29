from dataclasses import dataclass, field


@dataclass
class PluginVersionRouter:
    defaults: dict[str, str] = field(default_factory=dict)
    run_pins: dict[str, dict[str, str]] = field(default_factory=dict)

    def activate_default(self, plugin_id: str, version: str) -> None:
        self.defaults[plugin_id] = version

    def pin_run(self, run_id: str) -> dict[str, str]:
        # Run 开始时冻结默认插件版本快照，后续热升级/回滚不能改变同一次诊断的工具解析结果。
        snapshot = dict(self.defaults)
        self.run_pins[run_id] = snapshot
        return snapshot

    def resolve(self, plugin_id: str, run_id: str | None = None) -> str | None:
        # 有 run pin 时优先使用快照，保证证据链中的 plugin_version 可复现。
        if run_id and run_id in self.run_pins:
            return self.run_pins[run_id].get(plugin_id)
        return self.defaults.get(plugin_id)

    def rollback(self, plugin_id: str, version: str) -> None:
        self.defaults[plugin_id] = version
