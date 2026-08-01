"""EdgeLab configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONSTITUTION_PATH = _PROJECT_ROOT / "ARCHITECTURE_v1.md"


def _extract_yaml_block(text: str) -> str:
    start = text.index("```yaml") + len("```yaml")
    end = text.index("```", start)
    return text[start:end]


class Config:
    """YAML-backed project configuration."""

    def __init__(self, constitution_path: Path | None = None) -> None:
        self.constitution_path = Path(constitution_path or _DEFAULT_CONSTITUTION_PATH)
        text = self.constitution_path.read_text(encoding="utf-8")
        self._data: Dict[str, Any] = yaml.safe_load(_extract_yaml_block(text)) or {}

    def get(self, dotted_path: str, default: Any = None) -> Any:
        node = self._data
        for key in dotted_path.split("."):
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
        return node

    @property
    def account(self) -> Dict[str, Any]:
        return self._data.get("account", {})

    @property
    def internal_risk(self) -> Dict[str, Any]:
        return self._data.get("internal_risk", {})

    @property
    def strategy(self) -> Dict[str, Any]:
        return self._data.get("strategy", {})

    @property
    def environment(self) -> Dict[str, Any]:
        return self._data.get("environment", {})

    @property
    def validation_bar(self) -> Dict[str, Any]:
        return self._data.get("validation_bar", {})
