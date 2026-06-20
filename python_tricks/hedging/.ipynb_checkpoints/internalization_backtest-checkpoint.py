# internalization_backtest.py
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Protocol, Any

# ---------- Data model ----------
@dataclass
class FlowEvent:
    ts: pd.Timestamp         # 时间戳（tz-aware）
    instrument: str          # 品种，如 'EURUSD'
    side: int                # +1 客户买（我们卖），-1 客户卖（我们买）
    qty: float               # 数量（名义/基准单位）
    px: float                # 成交价（这里不强用）
    mid: float               # 当时中价（用于名义/成本）
    client_id: str           # 客户ID

# ---------- Strategy interface ----------
class Strategy(Protocol):
    def on_event(self, event: FlowEvent, state: Dict[str, Any]) -> List[Tuple[str, float]]:
        """返回[(instrument, qty), ...]；qty>0 对街卖出(减多头)，qty<0 对街买入(减空头)"""
        ...
    def on_time(self, now: pd.Timestamp, state: Dict[str, Any]) -> List[Tuple[str, float]]:
        return []

# ---------- Config ----------
@dataclass
class BacktestConfig:
    instruments: List[str]
    half_spread_bps: float = 0.5     # 外部对冲半点差（bps）
    impact_bps_per_mm: float = 0.2   # 线性冲击（每$1mm的bps）
    inv_penalty_per_mm: float = 1.0  # 库存时长罚则（$1mm·小时）
    risk_factors: Optional[Dict[str, Dict[str, float]]] = None  # 可选因子加载
    tz: str = "Europe/London"

# ---------- Simulator ----------
class InternalizationSimulator:
    def __init__(self, config: BacktestConfig, strategy: Strategy):
        self.cfg = config
        self.strategy = strategy
        self.state: Dict[str, Any] = {
            "inventory": {inst: 0.0 for inst in self.cfg.instruments},
            "last_ts": None,
            "factor_inventory": {} if config.risk_factors else None,
            "last_mid": {},
            "metrics": {
                "ext_hedge_cost": 0.0,
                "internalization_qty": {inst: 0.0 for inst in self.cfg.instruments},
                "ext_hedge_qty": {inst: 0.0 for inst in self.cfg.instruments},
                "inv_penalty": 0.0,
                "pnl_markout": 0.0
            }
        }

    def _apply_inventory_penalty(self, dt_hours: float):
        if self.cfg.risk_factors:
            instruments = self.cfg.instruments
            factors = list(self.cfg.risk_factors.keys())
            F = np.zeros((len(instruments), len(factors)))
            for i, inst in enumerate(instruments):
                for j, fac in enumerate(factors):
                    F[i, j] = self.cfg.risk_factors[fac].get(inst, 0.0)
            inv_vec = np.array([self.state["inventory"][inst] for inst in instruments])
            F_pinv = np.linalg.pinv(F)
            factor_inv = F_pinv @ inv_vec
            self.state["factor_inventory"] = {factors[j]: factor_inv[j] for j in range(len(factors))}
            inv_equiv_mm = np.sum(np.abs(factor_inv)) / 1e6
        else:
            inv_equiv_mm = sum(abs(v) for v in self.state["inventory"].values()) / 1e6
        self.state["metrics"]["inv_penalty"] += dt_hours * self.cfg.inv_penalty_per_mm * inv_equiv_mm

    def _external_hedge(self, instrument: str, qty: float, mid: float):
        if qty == 0: return
        notional = abs(qty) * mid
        spread_cost = (self.cfg.half_spread_bps / 1e4) * notional * 2
        impact_cost = (self.cfg.impact_bps_per_mm / 1e4) * (notional / 1e6) * notional
        self.state["metrics"]["ext_hedge_cost"] += spread_cost + impact_cost
        self.state["metrics"]["ext_hedge_qty"][instrument] += abs(qty)
        self.state["inventory"][instrument] -= qty  # 卖给市场：减少多头；买自市场：减少空头

    def step_time(self, now: pd.Timestamp):
        if self.state["last_ts"] is None:
            self.state["last_ts"] = now
            return
        dt = (now - self.state["last_ts"]).total_seconds() / 3600.0
        if dt > 0: self._apply_inventory_penalty(dt)
        self.state["last_ts"] = now

    def on_client_event(self, event: FlowEvent):
        self.step_time(event.ts)
        # 客户成交 = 内化：更新库存（客户买=我们卖 -> 库存减少）
        signed_qty = -event.side * event.qty
        self.state["inventory"][event.instrument] += signed_qty
        self.state["metrics"]["internalization_qty"][event.instrument] += abs(event.qty)
        self.state["last_mid"][event.instrument] = event.mid
        # 策略动作
        for inst, qty in self.strategy.on_event(event, self.state):
            self._external_hedge(inst, qty, event.mid)

    def on_time(self, now: pd.Timestamp):
        self.step_time(now)
        for inst, qty in self.strategy.on_time(now, self.state):
            mid = self.state["last_mid"].get(inst, 1.0)
            self._external_hedge(inst, qty, mid)

    def results(self): return self.state

# ---------- Strategies ----------
class HoldToEOD(Strategy):
    def __init__(self, eod_time: pd.Timestamp):
        self.eod = eod_time
        self.done = False
    def on_event(self, event: FlowEvent, state): return []
    def on_time(self, now: pd.Timestamp, state):
        if not self.done and now >= self.eod:
            self.done = True
            return [(inst, inv) for inst, inv in state["inventory"].items() if inv != 0]
        return []

class TimeBucketNetting(Strategy):
    def __init__(self, bucket_minutes: int = 30, tolerance_notional: float = 0.0):
        self.bucket = bucket_minutes
        self.tolerance = tolerance_notional
        self.next_cut: Optional[pd.Timestamp] = None
    def on_event(self, event: FlowEvent, state):
        if self.next_cut is None:
            self.next_cut = event.ts.floor(f"{self.bucket}min") + pd.Timedelta(minutes=self.bucket)
        return []
    def on_time(self, now: pd.Timestamp, state):
        if self.next_cut and now >= self.next_cut:
            actions = []
            for inst, inv in state["inventory"].items():
                mid = state["last_mid"].get(inst, 1.0)
                if abs(inv) * mid > self.tolerance:
                    actions.append((inst, inv))  # 清到0
            self.next_cut += pd.Timedelta(minutes=self.bucket)
            return actions
        return []

class ToleranceBandPartialHedge(Strategy):
    def __init__(self, band_notional: float = 1e6, decay: float = 0.5):
        self.band = band_notional
        self.decay = decay
    def on_event(self, event: FlowEvent, state):
        inv = state["inventory"][event.instrument]
        notional = abs(inv) * event.mid
        if notional > self.band:
            target_inv = np.sign(inv) * (self.band / event.mid)
            hedge_qty = (inv - target_inv) * self.decay
            return [(event.instrument, hedge_qty)]
        return []

class ProbabilisticWait(Strategy):
    """ 占位版：用常数λ估计在窗口内出现对手盘的概率；低于阈值就对冲一部分 """
    def __init__(self, horizon_minutes: int = 10, p_hold_threshold: float = 0.6, hedge_fraction: float = 0.5):
        self.horizon = horizon_minutes
        self.p_hold_threshold = p_hold_threshold
        self.hedge_fraction = hedge_fraction
    def on_event(self, event: FlowEvent, state):
        inv = state["inventory"][event.instrument]
        if inv == 0: return []
        lam = state.get("lambda_per_minute", {}).get(event.instrument, 0.05)  # 你可以换成Poisson/Hawkes估计
        p_arrival = 1 - np.exp(-lam * self.horizon)
        if p_arrival < self.p_hold_threshold:
            return [(event.instrument, inv * self.hedge_fraction)]
        return []

# ---------- Runner ----------
def run_backtest(flow_df: pd.DataFrame, strategy: Strategy, cfg: Optional[BacktestConfig] = None):
    if cfg is None:
        cfg = BacktestConfig(instruments=sorted(flow_df["instrument"].unique().tolist()))
    sim = InternalizationSimulator(cfg, strategy)
    for row in flow_df.sort_values("ts").itertuples(index=False):
        ev = FlowEvent(ts=row.ts, instrument=row.instrument, side=row.side, qty=row.qty,
                       px=row.px, mid=row.mid, client_id=row.client_id)
        sim.on_client_event(ev)
        sim.on_time(ev.ts)
    last_ts = flow_df["ts"].max()
    if last_ts is not None:
        sim.on_time(last_ts + pd.Timedelta(minutes=1))
    return sim.results()
