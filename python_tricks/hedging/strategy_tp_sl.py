
# strategy_tp_sl.py
"""
HybridInternalTPSSL
-------------------
A strategy that splits handling of inventory into:
1) Internalization-first (hold inside a tolerance band if desired)
2) External hedging upon *price* triggers: Take-Profit (TP) and Stop-Loss (SL)

Key ideas:
- Track a per-instrument signed inventory and its VWAP entry (rolling) as price anchor.
- Compute TP/SL thresholds around the anchor in *bps* or absolute terms.
- When mid crosses TP/SL in favorable/unfavorable direction, hedge a fraction of the inventory.
- Optional trailing stop that moves with favorable price.
- Optional cooldown to avoid over-trading.

Designed to work with InternalizationSimulator from internalization_backtest.py
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd

@dataclass
class TPSSLParams:
    tp_bps: float = 5.0              # take-profit threshold in bps from entry anchor
    sl_bps: float = 8.0              # stop-loss threshold in bps from entry anchor
    tp_fraction: float = 0.5         # fraction of CURRENT inventory to hedge on TP hit
    sl_fraction: float = 0.7         # fraction to hedge on SL hit
    trailing_tp: bool = False        # if True, anchor shifts favorably (trailing)
    trailing_sl: bool = False        # if True, stop trails favorably
    min_trade_qty: float = 0.0       # skip hedges below this qty
    tolerance_band_notional: float = 0.0  # optional: hold small inv to favor internalization
    cooldown_minutes: float = 0.0    # minimal time between successive hedges (per instrument)

class HybridInternalTPSSL:
    """
    For each instrument, we keep:
      - inv_vwap: rolling VWAP of current signed inventory (resets when inventory sign flips)
      - last_hedge_ts: last time we executed an external hedge (for cooldown)
      - best_favorable_mid: best price since entry for trailing logic
    Conventions:
      - Long inventory benefits from price UP moves; short benefits from price DOWN moves.
      - Entry anchor is inv_vwap. TP/SL are computed around it.
    """
    def __init__(self, params: TPSSLParams, eod_time: Optional[pd.Timestamp] = None):
        self.p = params
        self.eod_time = eod_time
        self.inv_vwap: Dict[str, float] = {}
        self.best_favorable_mid: Dict[str, float] = {}
        self.last_hedge_ts: Dict[str, pd.Timestamp] = {}
        self.last_sign: Dict[str, int] = {}

    # --- helpers ---
    def _bps_diff(self, px: float, ref: float) -> float:
        # signed bps of px vs ref: (px/ref - 1)*1e4
        return (px / ref - 1.0) * 1e4

    def _update_entry_anchor(self, inst: str, inv: float, mid: float, event_px: Optional[float]=None):
        sign = 0 if inv == 0 else (1 if inv > 0 else -1)
        last_sign = self.last_sign.get(inst, 0)

        if sign == 0:
            self.inv_vwap.pop(inst, None)
            self.best_favorable_mid.pop(inst, None)
            self.last_sign[inst] = 0
            return

        if sign != last_sign:
            # reset anchor on sign flip or from flat
            self.inv_vwap[inst] = mid if event_px is None else event_px
            self.best_favorable_mid[inst] = mid
            self.last_sign[inst] = sign
            return

        # same sign -> update VWAP toward current mid proportionally (approximation)
        # In practice, you can use executed prices vs clients; here we approximate with mid
        cur_vwap = self.inv_vwap.get(inst, mid)
        # light EWMA toward current mid to represent blended entry changes
        self.inv_vwap[inst] = 0.95 * cur_vwap + 0.05 * mid

        # update best favorable for trailing logic
        best = self.best_favorable_mid.get(inst, mid)
        if sign > 0:
            # long: favorable if price increases
            if mid > best: self.best_favorable_mid[inst] = mid
        else:
            # short: favorable if price decreases
            if mid < best: self.best_favorable_mid[inst] = mid

    def _cooldown_ok(self, inst: str, now: pd.Timestamp) -> bool:
        if self.p.cooldown_minutes <= 0:
            return True
        last = self.last_hedge_ts.get(inst, None)
        if last is None:
            return True
        dt_min = (now - last).total_seconds() / 60.0
        return dt_min >= self.p.cooldown_minutes

    def _maybe_trailing_adjust(self, inst: str, sign: int, anchor: float) -> float:
        # move anchor favorably if trailing flags enabled
        if sign == 0: return anchor
        best = self.best_favorable_mid.get(inst, anchor)
        if sign > 0 and self.p.trailing_tp:
            # long: move anchor up to best
            anchor = max(anchor, best)
        if sign < 0 and self.p.trailing_tp:
            # short: move anchor down to best
            anchor = min(anchor, best)
        # trailing stop: move stop closer after favorable move → implemented implicitly by changing anchor
        return anchor

    def _hedge_qty(self, inv: float, fraction: float) -> float:
        return inv * fraction  # signed

    # --- hooks ---
    def on_event(self, event, state: Dict[str, Any]) -> List[Tuple[str, float]]:
        inst = event.instrument
        mid = event.mid
        inv = state["inventory"][inst]

        # 1) 更新入场锚点 / 最优价（用于trailing）
        self._update_entry_anchor(inst, inv, mid, event_px=mid)

        # 2) 容忍带：小仓位先不动，倾向内部净额
        actions: List[Tuple[str, float]] = []
        if self.p.tolerance_band_notional > 0:
            notional = abs(inv) * mid
            if notional <= self.p.tolerance_band_notional:
                return actions  # 在带内直接等待 internalize

        # 3) 计算 TP / SL 命中并分层对冲
        sign = 0 if inv == 0 else (1 if inv > 0 else -1)
        if sign == 0:
            return actions

        if not self._cooldown_ok(inst, event.ts):
            return actions

        anchor = self.inv_vwap.get(inst, mid)
        anchor = self._maybe_trailing_adjust(inst, sign, anchor)

        # signed move in bps relative to anchor
        move_bps = self._bps_diff(mid, anchor)

        # Define favorable direction for TP:
        # long: move_bps > 0 is favorable; short: move_bps < 0 favorable
        tp_hit = (sign > 0 and move_bps >= self.p.tp_bps) or (sign < 0 and move_bps <= -self.p.tp_bps)
        sl_hit = (sign > 0 and move_bps <= -self.p.sl_bps) or (sign < 0 and move_bps >= self.p.sl_bps)

        hedge_fraction = 0.0
        if tp_hit and self.p.tp_fraction > 0:
            hedge_fraction = max(hedge_fraction, self.p.tp_fraction)
        if sl_hit and self.p.sl_fraction > 0:
            hedge_fraction = max(hedge_fraction, self.p.sl_fraction)

        if hedge_fraction > 0:
            qty = self._hedge_qty(inv, hedge_fraction)
            if abs(qty) >= self.p.min_trade_qty:
                actions.append((inst, qty))
                self.last_hedge_ts[inst] = event.ts

        return actions

    def on_time(self, now: pd.Timestamp, state: Dict[str, Any]) -> List[Tuple[str, float]]:
        # 可选：到 EOD 清仓
        if self.eod_time is not None and now >= self.eod_time and not state.get("_tp_sl_eod_done", False):
            state["_tp_sl_eod_done"] = True
            actions = []
            for inst, inv in state["inventory"].items():
                if inv != 0:
                    actions.append((inst, inv))
            return actions
        return []
