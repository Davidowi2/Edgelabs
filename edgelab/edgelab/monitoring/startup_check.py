"""Startup validation for EdgeLab (Phase 1, Module 5).

Before any trading logic runs, ``StartupValidator.run_all_checks()`` verifies
the configuration is safe. Errors are fatal (do NOT start). Warnings are
non-fatal (system may start, but the operator is told).

The validator reads a plain config dict. Risk limits are read from
``internal_risk`` (the live constitution) with a ``risk`` fallback so the same
code works against test fixtures. Only the standard library is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from edgelab.monitoring.logger import TradingLogger
from edgelab.risk.firm_presets import list_firm_presets

_PRESET_NAMES = set(list_firm_presets())


@dataclass
class StartupResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class StartupValidator:
    def __init__(self, config: Dict[str, Any], logger: TradingLogger) -> None:
        self.config = config or {}
        self._logger = logger

    # ----- helpers -----
    def _risk(self, key: str) -> Optional[float]:
        ir = self.config.get("internal_risk", {}) or {}
        if key in ir:
            return float(ir[key])
        r = self.config.get("risk", {}) or {}
        if key in r:
            return float(r[key])
        return None

    def _check(self, label: str, fn) -> Tuple[bool, str]:
        try:
            ok, msg = fn()
        except Exception as exc:  # noqa: BLE001 - validation must never crash startup
            ok, msg = False, f"{label} raised: {exc}"
        level = self._logger.info if ok else self._logger.error
        level("startup_check", check=label, passed=ok, message=msg)
        return ok, msg

    # ----- individual checks (each returns (bool, str)) -----
    def check_broker_time_configured(self) -> Tuple[bool, str]:
        offset = (self.config.get("broker") or {}).get("timezone_offset")
        if offset is None:
            return False, "broker.timezone_offset is not set"
        if str(offset).strip("+-") in ("", "0"):
            return True, "WARNING: broker timezone offset is 0 (possible misconfiguration: broker usually UTC+3)"
        return True, f"broker timezone offset configured: {offset}"

    def check_log_directory_writable(self, log_dir: Optional[str] = None) -> Tuple[bool, str]:
        import os
        import tempfile
        from pathlib import Path

        d = log_dir or (self.config.get("logging") or {}).get("log_dir") or tempfile.gettempdir()
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
            probe = Path(d) / ".write_test"
            probe.write_text("ok")
            probe.unlink()
            return True, f"log directory writable: {d}"
        except Exception as exc:  # noqa: BLE001
            return False, f"cannot write to log directory {d}: {exc}"

    def check_data_source_connected(self) -> Tuple[bool, str]:
        # We cannot auto-test a live broker without credentials; manual step.
        return True, "Data source check: manual verification required"

    def check_risk_limits_configured(self) -> Tuple[bool, str]:
        rpt = self._risk("risk_per_trade_pct")
        dll = self._risk("daily_loss_lock_pct")
        tdl = self._risk("total_dd_lock_pct")
        or_dd = self._risk("daily_dd_pct")
        or_tdd = self._risk("total_dd_pct")

        errors = []
        warnings = []
        if rpt is None:
            errors.append("risk_per_trade not configured")
        elif rpt <= 0:
            errors.append("risk_per_trade must be > 0")
        elif rpt > 0.02:
            errors.append(f"risk_per_trade {rpt} exceeds 2% safety cap")
        elif rpt > 0.01:
            warnings.append(f"risk_per_trade {rpt} is high (warn >1%)")

        if dll is None and or_dd is None:
            warnings.append("no daily loss limit configured")
        elif dll is not None and dll > 0.05:
            errors.append(f"daily_loss_limit {dll} exceeds 5% safety cap")

        if tdl is None and or_tdd is None:
            warnings.append("no max drawdown limit configured")
        elif tdl is not None and tdl > 0.10:
            errors.append(f"max_drawdown {tdl} exceeds 10% safety cap")

        if errors:
            return False, "; ".join(errors)
        if warnings:
            return True, "; ".join(warnings)
        return True, "risk limits within safe ranges"

    def check_analysis_config(self) -> Tuple[bool, str]:
        """Verify the analytical-core config is present.

        Per Phase 5a design: a missing/partial analysis config is a WARNING, not
        an error. The system can still run (fail-open) — it just won't have
        structure/anomaly/memory context for decisions.
        """
        analysis = self.config.get("analysis")
        if not isinstance(analysis, dict):
            return True, "WARNING: analysis config missing (brain context disabled)"
        return True, f"analysis config present (keys={list(analysis.keys())})"

    def check_regime_config(self) -> Tuple[bool, str]:
        """Verify the regime-detection config is present.

        Per Phase 6 design: a missing/partial regime config is a WARNING, not
        an error. The system can still run (fail-open) — it just has less
        market-context for the signal layer.
        """
        regime = self.config.get("regime")
        if not isinstance(regime, dict):
            return True, "WARNING: regime config missing (market-context disabled)"
        return True, f"regime config present (keys={list(regime.keys())})"

    def check_execution_config(self) -> Tuple[bool, str]:
        """Verify the Phase 8 execution-quality config is present and sane.

        A missing execution config is a WARNING (fail-open): the system can
        still run, but without the spread guard / circuit breaker / retry
        safety nets that protect it during live broker conditions. The
        breaker thresholds are also sanity-checked so a zero/negative
        failure_threshold cannot silently disable protection.
        """
        exec_cfg = self.config.get("execution")
        if not isinstance(exec_cfg, dict):
            return True, "WARNING: execution config missing (retry/circuit/spread-guard disabled)"
        spread = exec_cfg.get("spread", {})
        if not isinstance(spread, dict):
            return True, "WARNING: execution.spread missing (spread guard disabled)"
        cb = exec_cfg.get("circuit_breaker", {})
        threshold = cb.get("failure_threshold", 5)
        try:
            threshold = int(threshold)
        except (TypeError, ValueError):
            return False, f"execution.circuit_breaker.failure_threshold invalid: {threshold!r}"
        if threshold <= 0:
            return False, "execution.circuit_breaker.failure_threshold must be > 0"
        return True, (f"execution config present (spread_guard+circuit_breaker+retry, "
                      f"failure_threshold={threshold})")

    def check_risk_config(self) -> Tuple[bool, str]:
        """Verify the account-level risk config is safe to trade with.

        Per Phase 3 design: a missing/partial risk config is a WARNING, not an
        error. The system can still run (fail-open) — it just will not be
        prop-firm-safe until the operator fixes the config.
        """
        risk = self.config.get("risk")
        if not isinstance(risk, dict):
            return True, "WARNING: risk config missing (account-level protection disabled)"
        if not isinstance(risk.get("initial_balance"), (int, float)) or risk.get("initial_balance") <= 0:
            return True, "WARNING: risk.initial_balance missing/invalid (account protection disabled)"
        preset = risk.get("firm_preset")
        if preset not in (None,) and preset not in _PRESET_NAMES:
            return True, f"WARNING: unknown firm_preset {preset!r} (account protection disabled)"
        return True, f"risk config present (preset={preset})"

    def check_news_filter_configured(self) -> Tuple[bool, str]:
        cmap = (self.config.get("news_filter") or {}).get("currency_map") or {}
        if not cmap:
            return False, "news_filter.currency_map is empty/missing"
        return True, f"news filter currency map set for {len(cmap)} symbol(s)"

    def check_news_calendar_file(self) -> Tuple[bool, str]:
        """Verify the static news calendar file exists and is readable.

        Per Phase 2 design: a missing calendar is a WARNING, not an error.
        The system can still trade (fail-open) without news filtering, just
        less safely. The currency map check above remains the hard gate.
        """
        from pathlib import Path

        path = (self.config.get("news") or {}).get("static_calendar_path")
        if not path:
            return True, "WARNING: news.static_calendar_path not set (no news filtering)"
        p = Path(path)
        if not p.exists():
            return True, f"WARNING: news calendar file missing: {path} (trading without news filter)"
        try:
            text = p.read_text(encoding="utf-8")
            if not text.strip():
                return True, f"WARNING: news calendar file empty: {path}"
            return True, f"news calendar file present: {path}"
        except Exception as exc:  # noqa: BLE001
            return True, f"WARNING: cannot read news calendar {path}: {exc}"

    def check_account_type(self) -> Tuple[bool, str]:
        acct = self.config.get("account") or {}
        atype = acct.get("type")
        if atype is None:
            return False, "account.type is not set (demo vs live unknown)"
        if atype == "live" and not acct.get("confirmed"):
            return True, "LIVE account without confirmed config (warn: verify before trading real money)"
        return True, f"account type: {atype}"

    def check_inactivity_prevention(self) -> Tuple[bool, str]:
        last = (self.config.get("inactivity") or {}).get("last_trade_timestamp")
        if not last:
            return False, "inactivity.last_trade_timestamp not initialized (risk of 30-day auto-closure)"
        return True, "inactivity tracking initialized"

    # ----- aggregate -----
    def run_all_checks(self) -> StartupResult:
        checks = [
            ("broker_time", self.check_broker_time_configured),
            ("log_dir", lambda: self.check_log_directory_writable()),
            ("data_source", self.check_data_source_connected),
            ("risk_limits", self.check_risk_limits_configured),
            ("risk_config", self.check_risk_config),
            ("news_filter", self.check_news_filter_configured),
            ("news_calendar", self.check_news_calendar_file),
            ("analysis_config", self.check_analysis_config),
            ("regime_config", self.check_regime_config),
            ("execution_config", self.check_execution_config),
            ("account_type", self.check_account_type),
            ("inactivity", self.check_inactivity_prevention),
        ]
        errors: List[str] = []
        warnings: List[str] = []
        for label, fn in checks:
            ok, msg = self._check(label, fn)
            if not ok:
                errors.append(f"{label}: {msg}")
            elif "warn" in msg.lower():
                warnings.append(f"{label}: {msg}")
        passed = not errors
        self._logger.info(
            "startup_validation_complete", passed=passed, n_errors=len(errors), n_warnings=len(warnings)
        )
        return StartupResult(passed=passed, errors=errors, warnings=warnings)

    def _checks_run(self) -> List[Tuple[str, object]]:
        """Expose the ordered check plan (for tests/auditing)."""
        return [
            ("broker_time", self.check_broker_time_configured),
            ("log_dir", lambda: self.check_log_directory_writable()),
            ("data_source", self.check_data_source_connected),
            ("risk_limits", self.check_risk_limits_configured),
            ("risk_config", self.check_risk_config),
            ("news_filter", self.check_news_filter_configured),
            ("news_calendar", self.check_news_calendar_file),
            ("analysis_config", self.check_analysis_config),
            ("regime_config", self.check_regime_config),
            ("execution_config", self.check_execution_config),
            ("account_type", self.check_account_type),
            ("inactivity", self.check_inactivity_prevention),
        ]
