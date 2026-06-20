
# combined_strategy.py
"""
CombinedToleranceProb Strategy
-----------------------------
A strategy that combines:
1) Tolerance band inventory control
2) Layered partial hedging when inventory exceeds band
3) Probabilistic "wait" logic to reduce hedging if the chance of offsetting client flow is high

This class is designed to plug into the InternalizationSimulator from internalization_backtest.py.
It only relies on the simulator calling:
  - on_event(event, state) -> List[(instrument, qty)]
  - on_time(now, state) -> List[(instrument, qty)]

State conventions (from simulator):
- state["inventory"][instrument]: current signed inventory (qty units). Long>0, Short<0
- state["last_mid"][instrument]: last known mid price
- Optional: state["lambda_per_minute"][instrument]: estimated per-minute arrival rate of offsetting client flow.
  If not present, we use a fallback constant.
"""

from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd

class CombinedToleranceProb:
    def __init__(
        self,
        band_notional: float = 1e6,
        layers: List[Tuple[float, float]] = None,
        horizon_minutes: int = 10,
        hold_threshold: float = 0.6,
        wait_discount: float = 0.5,
        inside_fraction: float = 0.0,
        min_trade_qty: float = 0.0,
        eod_time: Optional[pd.Timestamp] = None,
        fallback_lambda_per_min: float = 0.05,
    ):
        """
        Args:
          band_notional: tolerance band size in notional terms (e.g., $1e6)
          layers: list of (multiple, hedge_fraction) sorted ascending by multiple.
                  multiple is |inv_notional| / band_notional threshold.
                  hedge_fraction applies to the *excess* over the band.
                  Example: [(1.0, 0.4), (2.0, 0.7), (3.0, 1.0)]
          horizon_minutes: lookahead window (minutes) for offset probability
          hold_threshold: if P(offset in horizon) >= hold_threshold -> we "wait" more (reduce hedging)
          wait_discount: factor in [0,1]; when we decide to wait, effective hedge_fraction *= (1 - wait_discount)
          inside_fraction: when inside the band but P(offset) < hold_threshold, hedge this fraction of current inv
          min_trade_qty: do not place hedges with absolute qty below this threshold (to avoid dust trades)
          eod_time: if provided, flatten any remaining inventory at or after EOD in on_time()
          fallback_lambda_per_min: used if state doesn't provide lambda_per_minute for the instrument
        """
        self.band_notional = band_notional
        self.layers = layers or [(1.0, 0.4), (2.0, 0.7), (3.0, 1.0)]
        self.horizon = horizon_minutes
        self.hold_threshold = hold_threshold
        self.wait_discount = wait_discount
        self.inside_fraction = inside_fraction
        self.min_trade_qty = min_trade_qty
        self.eod_time = eod_time
        self.fallback_lambda = fallback_lambda_per_min

        # ensure layers sorted by multiple
        self.layers = sorted(self.layers, key=lambda x: x[0])

    def _p_arrival(self, instrument: str, state: Dict[str, Any]) -> float:
        lam = state.get("lambda_per_minute", {}).get(instrument, self.fallback_lambda)
        return 1 - np.exp(-lam * self.horizon)

    def _maybe_round(self, qty: float) -> float:
        if abs(qty) < self.min_trade_qty:
            return 0.0
        return qty

    def on_event(self, event, state: Dict[str, Any]) -> List[Tuple[str, float]]:
        inst = event.instrument
        inv = state["inventory"][inst]
        mid = state.get("last_mid", {}).get(inst, event.mid if hasattr(event, "mid") else 1.0)
        notional = abs(inv) * mid

        # Probability of offsetting flow
        p_arrival = self._p_arrival(inst, state)
        wait_mode = (p_arrival >= self.hold_threshold)

        actions: List[Tuple[str, float]] = []

        # Case A: within band -> maybe small hedge if probability to offset is low
        if notional <= self.band_notional:
            if self.inside_fraction > 0 and not wait_mode and inv != 0:
                qty = inv * self.inside_fraction
                qty = self._maybe_round(qty)
                if qty != 0:
                    actions.append((inst, qty))
            return actions

        # Case B: outside band -> layered partial hedge on the EXCESS portion
        # excess inventory in qty terms
        target_edge_qty = np.sign(inv) * (self.band_notional / mid)
        excess_qty = inv - target_edge_qty  # signed
        excess_abs = abs(excess_qty)

        # pick layer by multiple
        multiple = notional / self.band_notional
        hedge_frac = 0.0
        for lvl, frac in self.layers:
            if multiple >= lvl:
                hedge_frac = frac
            else:
                break

        # apply wait discount if we believe offsetting flow likely arrives
        if wait_mode:
            hedge_frac *= (1.0 - self.wait_discount)

        qty = excess_qty * hedge_frac
        qty = self._maybe_round(qty)
        if qty != 0:
            actions.append((inst, qty))

        return actions

    def on_time(self, now: pd.Timestamp, state: Dict[str, Any]) -> List[Tuple[str, float]]:
        # Optional: clean up at EOD
        if self.eod_time is not None and now >= self.eod_time and not state.get("_combined_eod_done", False):
            state["_combined_eod_done"] = True
            actions = []
            for inst, inv in state["inventory"].items():
                if inv != 0:
                    actions.append((inst, inv))
            return actions
        return []
