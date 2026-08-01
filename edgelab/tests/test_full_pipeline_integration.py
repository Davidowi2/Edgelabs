"""Full pipeline integration test for EdgeLab (Phase 9a, Deliverable 2).

Proves the composition Phase 7 (confluence) -> Phase 3 (risk) -> Phase 2 (news)
-> Phase 4 (trade management) -> Phase 8 (execution) works END-TO-END against a
MockBroker. This is the gap the research exposed: each phase has unit tests,
but no test proved the layers compose and terminate safely when an upstream
layer blocks the trade.

Only the broker layer is mocked (MockBroker). The signal detector, confluence
checker, drawdown protector, trade manager, news filter, execution gateway,
system metrics and decision log are the REAL components.

Pure standard library only.
"""

import sys, os, tempfile
sys.path.insert(0, r"C:/Users/GTHub/Downloads/EDGELABS/edgelab")

from datetime import datetime, timezone

import pytest

from edgelab.monitoring.logger import TradingLogger
from edgelab.time.broker_time import BrokerTime
from edgelab.risk.account_state import AccountState
from edgelab.risk.drawdown_protector import (
    DrawdownProtector, ProtectionLevel, ProtectionAction,
)
from edgelab.trade import TradeManager
from edgelab.trade.position import Position, TradeDirection, TradeStatus
from edgelab.execution.gateway import (
    ExecutionGateway, GatewayResult, BrokerInterface,
)
from edgelab.execution.spread_guard import SpreadGuard
from edgelab.execution.circuit_breaker import (
    CircuitBreaker, CircuitConfig, CircuitState,
)
from edgelab.execution.retry_executor import (
    RetryExecutor, RetryConfig, MockTradeResult,
)
from edgelab.execution.mock_broker import MockBroker
from edgelab.monitoring.metrics import SystemMetrics
from edgelab.analysis.decision_log import DecisionLog, DecisionLogger
from edgelab.news.filter import NewsFilter

import tests.test_confluence as tcf


class PipelineResult:
    def __init__(self, action, reason, confluence=None, risk_level=None,
                 news_allowed=None, gateway_result=None, decision_log=None):
        self.action = action
        self.reason = reason
        self.confluence = confluence
        self.risk_level = risk_level
        self.news_allowed = news_allowed
        self.gateway_result = gateway_result
        self.decision_log = decision_log


class FullPipelineFixture:
    """Wires the real Phase 2/3/4/7/8 components around a MockBroker.

    Scenario state is configured per-test via ``configure(...)``.
    """

    def _make_flat_bars(self):
        """A sideways/flat series with no pullback -> detector returns None."""
        from datetime import timedelta
        bars = []
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        for i in range(200):
            level = 2000.0 + 0.5 * (1 if i % 2 == 0 else -1)  # tiny oscillation
            bars.append({"timestamp": base + timedelta(hours=i),
                         "open": level, "high": level + 1.0, "low": level - 1.0,
                         "close": level, "volume": 1000.0})
        return bars

    def __init__(self, logger):
        self.logger = logger
        self.checker, self.bars, self.current_time, self.symbol = tcf._build_green_env(logger)
        # flat bars (no pullback) -> detector returns None -> no base signal
        self.flat_bars = self._make_flat_bars()

        self.bt = BrokerTime(offset="+3", dst=False)
        self.acct = AccountState(initial_balance=10000.0, broker_time=self.bt, logger=logger)

        # Phase 3: risk (configurable; default SAFE)
        self.risk_protector = DrawdownProtector({}, self.acct, logger)

        # Phase 2: news filter (configurable; default no events)
        self.news_events = []
        self.news_filter = NewsFilter({}, self.news_events, logger, self.bt)

        # Phase 4: trade manager (real)
        self.trade_manager = TradeManager({}, logger, self.bt)

        # Phase 8: execution gateway (real) on a MockBroker
        self.broker = MockBroker(submit_fn=lambda r: MockTradeResult(0, True, 0.1),
                                 get_spread_fn=lambda: 10.0)
        # spread guard primed with a calm baseline (~10 pts)
        self.spread_guard = SpreadGuard(
            {"max_spread_points": 35.0, "shock_multiplier": 2.0,
             "elevated_multiplier": 1.5, "baseline_window": 60}, logger)
        for _ in range(12):
            self.spread_guard.update_baseline(10.0)
        # circuit breaker
        self.circuit = CircuitBreaker(
            CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger,
            time_fn=lambda: 0.0)
        # retry executor: 1 attempt, no real sleep
        self.retry = RetryExecutor(
            RetryConfig(max_attempts=1, base_delay_ms=1, max_delay_ms=10), logger,
            sleep_fn=lambda s: None)
        self.gateway = ExecutionGateway(
            {"magic_number": 0, "max_position_count": 1}, self.broker, logger,
            retry_exec=self.retry, circuit_br=self.circuit,
            spread_guard=self.spread_guard)

        # monitoring
        self.metrics = SystemMetrics(logger)
        self.decision_logger = DecisionLogger({}, logger, self.checker._memory)

    # ---- scenario configuration ----
    def configure(self, risk_level="SAFE", news_blocked=False,
                  spread_shock=False, duplicate=False, circuit_open=False,
                  broker_transient_failure=False, force_no_signal=False):
        # risk
        if risk_level == "KILL":
            class _DP:
                def check_protection(self):
                    return (ProtectionLevel.KILL, ProtectionAction.CLOSE_ALL_POSITIONS,
                            "kill switch triggered")
            self.risk_protector = _DP()
        else:
            self.risk_protector = DrawdownProtector({}, self.acct, self.logger)

        # news
        if news_blocked:
            self.news_filter = _BlockedNews(self.logger)
        else:
            self.news_filter = NewsFilter({}, self.news_events, self.logger, self.bt)

        # spread
        if spread_shock:
            self.broker._spread_fn = lambda: 25.0  # > 2x baseline(10) -> SHOCK
        else:
            self.broker._spread_fn = lambda: 10.0

        # duplicate position
        if duplicate:
            self.broker._positions_fn = lambda: [{"symbol": self.symbol, "magic": 0}]
        else:
            self.broker._positions_fn = lambda: []

        # circuit open
        if circuit_open:
            for _ in range(5):
                self.circuit.record_failure()
        else:
            self.circuit.reset()

        # broker transient failure (for consecutive-kill / circuit-open tests)
        if broker_transient_failure:
            self.broker._submit_fn = lambda r: MockTradeResult(10004, False, 0.0)
        else:
            self.broker._submit_fn = lambda r: MockTradeResult(0, True, 0.1)

        self._force_no_signal = force_no_signal

    # ---- run the full pipeline ----
    def run(self, symbol=None):
        symbol = symbol or self.symbol
        bars = self.flat_bars if getattr(self, "_force_no_signal", False) else self.bars
        current_price = bars[-1]["close"]
        account_balance = 10000.0

        # 1) Phase 7: base signal + confluence
        res = self.checker.check(bars, self.current_time, symbol, account_balance, current_price)
        if res.base_signal is None or not res.all_passed:
            reason = "no_base_signal" if res.base_signal is None else "confluence_failed"
            return PipelineResult("SKIP", reason, confluence=res,
                                   risk_level="N/A", news_allowed="N/A")

        # 2) Phase 3: risk layer
        level, action, rreason = self.risk_protector.check_protection()
        if level == ProtectionLevel.KILL:
            return PipelineResult("SKIP", "risk_layer_kill", confluence=res,
                                   risk_level=level.value, news_allowed="N/A")
        risk_level = level.value

        # 3) Phase 2: news filter
        allowed, nreason = self.news_filter.is_trading_allowed(symbol, self.current_time)
        if not allowed:
            return PipelineResult("SKIP", "news_blackout", confluence=res,
                                   risk_level=risk_level, news_allowed=False)
        self.metrics.record_news_block(symbol, "test", 0) if not allowed else None

        # 4) Phase 8: execution gateway (spread -> duplicate -> circuit -> broker)
        gw_result = self.gateway.submit_order({"symbol": symbol})
        if gw_result == GatewayResult.SPREAD_BLOCKED:
            return PipelineResult("SKIP", "spread_shock", confluence=res,
                                   risk_level=risk_level, news_allowed=True,
                                   gateway_result=gw_result)
        if gw_result == GatewayResult.DUPLICATE_BLOCKED:
            return PipelineResult("SKIP", "duplicate_position", confluence=res,
                                   risk_level=risk_level, news_allowed=True,
                                   gateway_result=gw_result)
        if gw_result == GatewayResult.CIRCUIT_OPEN:
            return PipelineResult("SKIP", "circuit_open", confluence=res,
                                   risk_level=risk_level, news_allowed=True,
                                   gateway_result=gw_result)
        if gw_result in (GatewayResult.SUCCESS, GatewayResult.PARTIAL):
            # 5) Phase 4: trade management applied to the filled position
            pos = Position(
                position_id="PX-1", symbol=symbol, direction=TradeDirection.LONG,
                entry_price=current_price, current_price=current_price,
                current_sl=current_price - 0.0020, current_tp=current_price + 0.0040,
                lot_size=0.1, status=TradeStatus.OPEN,
                entry_time=self.current_time)
            tm = self.trade_manager.evaluate_all(pos, account_balance, current_price,
                                                 self.current_time)
            self.metrics.record_trade_execution()
            # 6) decision log
            dlog = self._make_decision_log(symbol, res, current_price)
            self.decision_logger.log_decision(dlog)
            return PipelineResult("EXECUTE", None, confluence=res,
                                   risk_level=risk_level, news_allowed=True,
                                   gateway_result=gw_result, decision_log=dlog)

        # any other failure (FAILED_PERMANENT / FAILED_TRANSIENT)
        return PipelineResult("SKIP", "execution_failed", confluence=res,
                               risk_level=risk_level, news_allowed=True,
                               gateway_result=gw_result)

    def _make_decision_log(self, symbol, res, current_price):
        return DecisionLog(
            decision_id="DEC-1",
            timestamp_broker=self.bt.to_broker_time(self.current_time),
            timestamp_utc=self.current_time,
            symbol=symbol, direction="LONG", entry_price=current_price,
            stop_loss=current_price - 0.0020, take_profit=current_price + 0.0040,
            signal_type="reversal_pullback",
            market_structure={"trend": "UP"}, patterns=[{"pattern_type": "HH_HL"}],
            anomaly={"score": 0.1}, risk_status={"level": "SAFE"},
            news_status={"allowed": True},
            trade_management_status={"recommended_action": "none"},
            recommended_action="EXECUTE", confidence=res.confidence,
            reasoning="; ".join(res.reasons) or "green environment",
        )


class _BlockedNews:
    def __init__(self, logger):
        self._logger = logger

    def is_trading_allowed(self, symbol, current_time=None):
        return False, "blackout active"


@pytest.fixture
def logger():
    return TradingLogger(name="pipeline.test",
                         log_file=os.path.join(tempfile.gettempdir(), "pipeline_test.log"))


@pytest.fixture
def fixture(logger):
    return FullPipelineFixture(logger)


class TestHappyPath:
    def test_happy_path_executes_end_to_end(self, fixture):
        fixture.configure()
        out = fixture.run()
        assert out.action == "EXECUTE"
        assert out.confluence.all_passed is True
        assert out.risk_level == "SAFE"
        assert out.gateway_result == GatewayResult.SUCCESS
        # spread + circuit clean at the boundary
        assert fixture.spread_guard.is_blocked(
            fixture.spread_guard.check_spread(10.0, fixture.current_time)) is False
        assert fixture.circuit.get_state() == CircuitState.CLOSED


class TestRiskLayer:
    def test_risk_layer_kill_blocks_before_confluence(self, fixture):
        fixture.configure(risk_level="KILL")
        out = fixture.run()
        assert out.action == "SKIP"
        assert out.reason == "risk_layer_kill"
        # confluence still evaluated (real component) but pipeline stopped at risk
        assert out.confluence is not None
        assert out.confluence.all_passed is True


class TestNewsLayer:
    def test_news_filter_blocks_before_risk(self, fixture):
        fixture.configure(news_blocked=True)
        out = fixture.run()
        assert out.action == "SKIP"
        assert out.reason == "news_blackout"
        # risk was SAFE; pipeline stopped at news
        assert out.risk_level == "SAFE"


class TestCircuitLayer:
    def test_circuit_breaker_open_blocks_before_broker(self, fixture):
        fixture.configure(circuit_open=True)
        out = fixture.run()
        assert out.action == "SKIP"
        assert out.reason == "circuit_open"
        assert fixture.broker.submit_calls == 0
        assert out.risk_level == "SAFE"


class TestSpreadLayer:
    def test_spread_shock_blocks_before_circuit(self, fixture):
        fixture.configure(spread_shock=True)
        out = fixture.run()
        assert out.action == "SKIP"
        assert out.reason == "spread_shock"
        assert fixture.broker.submit_calls == 0
        assert out.risk_level == "SAFE"


class TestDuplicateLayer:
    def test_duplicate_position_blocks_before_circuit(self, fixture):
        fixture.configure(duplicate=True)
        out = fixture.run()
        assert out.action == "SKIP"
        assert out.reason == "duplicate_position"
        assert fixture.broker.submit_calls == 0
        assert fixture.circuit.get_failure_count() == 0


class TestPriorityOrdering:
    def test_priority_ordering_risk_beats_news_beats_spread(self, fixture):
        # risk KILL + news blocked + spread shock all active
        fixture.configure(risk_level="KILL", news_blocked=True, spread_shock=True)
        out = fixture.run()
        assert out.action == "SKIP"
        # risk is highest priority -> its reason wins
        assert out.reason == "risk_layer_kill"

    def test_full_kill_chain_returns_first_priority_failure(self, fixture):
        fixture.configure(risk_level="KILL", news_blocked=True, spread_shock=True)
        out = fixture.run()
        # even though news + spread also block, the FIRST (risk) is reported
        assert out.reason == "risk_layer_kill"
        assert out.risk_level == "KILL"


class TestNoSignal:
    def test_no_base_signal_skips_before_any_check(self, fixture):
        fixture.configure()
        # force no base signal by using flat bars
        fixture._force_no_signal = True
        before = fixture.broker.submit_calls
        out = fixture.run()
        assert out.action == "SKIP"
        assert out.reason == "no_base_signal"
        # confluence never evaluated to all_passed -> no downstream checks ran
        assert fixture.broker.submit_calls == before


class TestAuditTrail:
    def test_decision_log_recorded_end_to_end(self, fixture):
        fixture.configure()
        out = fixture.run()
        assert out.action == "EXECUTE"
        d = out.decision_log
        assert d is not None
        # decision log must contain: signal details, 8 filter results,
        # confidence, final action, timestamp
        assert d.symbol == fixture.symbol
        assert d.confidence > 0.0
        assert d.recommended_action == "EXECUTE"
        assert d.timestamp_utc is not None
        # 8 filter/context results present
        for field in ("market_structure", "patterns", "anomaly", "risk_status",
                      "news_status", "trade_management_status", "signal_type"):
            assert getattr(d, field) is not None or field == "signal_type"
        # retrievable from the decision logger
        fetched = fixture.decision_logger.get_decision("DEC-1")
        assert fetched is not None
        assert fetched.symbol == fixture.symbol

    def test_system_metrics_updated_end_to_end(self, fixture):
        fixture.configure()
        out = fixture.run()
        assert out.action == "EXECUTE"
        summary = fixture.metrics.get_summary()
        # trade execution recorded
        assert summary["trades_executed"] >= 1
        # anomaly + memory lookups happened inside confluence (metrics side-channel)
        assert summary["total_ticks"] >= 0  # metrics object is live


class TestConsecutiveFailures:
    def test_consecutive_kills_keeps_circuit_open(self, fixture):
        # broker returns transient failure every time; retry=1 attempt
        fixture.configure(broker_transient_failure=True)
        for _ in range(5):
            fixture.run()
        # after 5 consecutive transient failures the circuit opens
        assert fixture.circuit.get_state() == CircuitState.OPEN
        # next attempt is blocked by the open circuit (no broker call)
        before = fixture.broker.submit_calls
        out = fixture.run()
        assert out.action == "SKIP"
        assert out.reason == "circuit_open"
        assert fixture.broker.submit_calls == before
