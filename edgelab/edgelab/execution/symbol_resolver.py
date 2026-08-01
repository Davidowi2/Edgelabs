"""Symbol resolution for EdgeLab (Phase 9b, Module 1).

Brokers name the same instrument differently: XAUUSD, XAUUSD.r, XAUUSDm,
GOLDm, XAUUSD.i, GOLD, ... This resolver maps any broker-specific symbol back
to the canonical logical name the rest of the system trades on. Pure standard
library only.
"""

from __future__ import annotations

from typing import List

from edgelab.monitoring.logger import TradingLogger


class SymbolNotFoundError(Exception):
    """Raised when a symbol cannot be mapped to a known canonical name."""


class SymbolResolver:
    def __init__(self, config: dict, logger: TradingLogger) -> None:
        cfg = config or {}
        self._logger = logger
        self.canonical_name = str(cfg.get("canonical_name", "XAUUSD")).upper()
        # Alias list. When the caller supplies broker_aliases, they REPLACE the
        # defaults entirely (custom brokers). Otherwise we derive a sensible
        # default set from the canonical name: the canonical plus the common
        # broker suffixes (.r / m / .i / .pro). For gold (XAUUSD) we also
        # recognize the legacy "GOLD" / "GOLDm" spellings.
        if "broker_aliases" in cfg and cfg["broker_aliases"]:
            self.broker_aliases: List[str] = list(cfg["broker_aliases"])
        else:
            c = self.canonical_name
            derived = [c, f"{c}.r", f"{c}m", f"{c}.i", f"{c}.pro"]
            if c == "XAUUSD":
                derived += ["GOLD", "GOLDm"]
            self.broker_aliases = derived
        self.suffix_pattern = cfg.get("suffix_pattern", "rstrip_alpha_after_dot")

    def resolve(self, canonical_or_alias: str) -> str:
        raw = str(canonical_or_alias).strip()
        # strip stray leading/trailing dots (e.g. ".XAUUSD")
        cleaned = raw.strip(".")
        if not cleaned:
            raise SymbolNotFoundError(raw)
        upper = cleaned.upper()
        # Every recognized token is either the canonical name or one of its
        # aliases (the alias list already enumerates suffix variants such as
        # "XAUUSD.r", "XAUUSDm", "GOLDm"). The starts-with rule extends matching
        # to suffixes not explicitly listed, but it applies to ALIASES only —
        # never to the bare canonical, so a custom alias set is not polluted by
        # the default canonical spilling onto unrelated broker symbols.
        known = [self.canonical_name] + [str(a).upper() for a in self.broker_aliases]
        if upper in known:
            return self.canonical_name
        alias_roots = [str(a).upper() for a in self.broker_aliases]
        if any(upper.startswith(name) for name in alias_roots):
            return self.canonical_name
        self._logger.warning("symbol not resolved", input=raw,
                             canonical=self.canonical_name)
        raise SymbolNotFoundError(raw)

    def list_candidates(self) -> List[str]:
        return [self.canonical_name] + [str(a) for a in self.broker_aliases]

    def validate_broker_symbol(self, broker_symbol: str) -> bool:
        try:
            self.resolve(broker_symbol)
            return True
        except SymbolNotFoundError:
            return False
