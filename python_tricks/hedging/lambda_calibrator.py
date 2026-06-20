
# lambda_calibrator.py
"""
Lambda calibrators for client flow arrival rates.
Provides online estimators you can plug into the internalization_backtest simulator.

Two robust options:
1) RollingPoissonCalibrator: MLE over a rolling time window (lambda = count / window_minutes)
2) EWMACalibrator: exponential moving average over inter-arrival times

Also includes a small "LambdaManager" that keeps per-(instrument, sign) stats and
exposes: update(event), get_lambda(instrument, sign), and an adapter to write
state["lambda_per_minute"][instrument] for your strategies that only need per-instrument
opposite-flow intensity.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np

@dataclass
class FlowAtom:
    ts: pd.Timestamp
    instrument: str
    side: int   # +1 client buys (we sell), -1 client sells (we buy)
    qty: float

class RollingPoissonCalibrator:
    """
    Poisson MLE in a sliding window: lambda_hat = count / window_minutes
    Separate tracking by (instrument, side) so you can ask for the opposite side.
    """
    def __init__(self, window_minutes: int = 15, min_obs: int = 3):
        self.window = pd.Timedelta(minutes=window_minutes)
        self.min_obs = min_obs
        self.buffers: Dict[Tuple[str, int], List[pd.Timestamp]] = {}

    def update(self, event: FlowAtom):
        key = (event.instrument, event.side)
        self.buffers.setdefault(key, []).append(event.ts)

    def get_lambda_per_min(self, instrument: str, side: int, now: Optional[pd.Timestamp] = None) -> Optional[float]:
        key = (instrument, side)
        if key not in self.buffers:
            return None
        ts_list = self.buffers[key]
        if not ts_list:
            return None
        if now is None:
            now = ts_list[-1]
        # drop old
        cutoff = now - self.window
        # Keep only events within window
        i = 0
        while i < len(ts_list) and ts_list[i] < cutoff:
            i += 1
        if i > 0:
            del ts_list[:i]
        n = len(ts_list)
        if n < self.min_obs:
            return None
        minutes = max(self.window.total_seconds() / 60.0, 1e-6)
        return n / minutes

class EWMACalibrator:
    """
    EWMA on arrivals: update intensity per minute using decay by half-life.
    Uses a simple discrete-time approximation at event timestamps.
    """
    def __init__(self, half_life_minutes: float = 10.0, init_lambda_per_min: float = 0.02):
        self.lambda_hat: Dict[Tuple[str, int], float] = {}
        self.last_ts: Dict[Tuple[str, int], pd.Timestamp] = {}
        self.half_life = half_life_minutes
        self.alpha_per_min = np.log(2) / max(half_life_minutes, 1e-6)  # decay rate

        self.init_lambda = init_lambda_per_min

    def update(self, event: FlowAtom):
        key = (event.instrument, event.side)
        lam = self.lambda_hat.get(key, self.init_lambda)
        last = self.last_ts.get(key, None)

        if last is None:
            # First observation
            self.lambda_hat[key] = lam + 1.0  # strong uptick on first hit; will decay after
            self.last_ts[key] = event.ts
            return

        dt_min = max((event.ts - last).total_seconds() / 60.0, 1e-9)
        # Exponential decay of intensity between events
        lam *= np.exp(-self.alpha_per_min * dt_min)
        # Arrival shock: add one-event impulse spread over one minute equivalent
        lam += 1.0
        self.lambda_hat[key] = lam
        self.last_ts[key] = event.ts

    def get_lambda_per_min(self, instrument: str, side: int, now: Optional[pd.Timestamp] = None) -> float:
        key = (instrument, side)
        lam = self.lambda_hat.get(key, self.init_lambda)
        if now is not None and key in self.last_ts:
            dt_min = max((now - self.last_ts[key]).total_seconds() / 60.0, 0.0)
            lam *= np.exp(-self.alpha_per_min * dt_min)
        return lam

class LambdaManager:
    """
    Manages one or more calibrators; by default, tries Poisson first then EWMA fallbacks.
    Keeps per-(instrument, side) stats. Provides:
      - update(event)
      - get_lambda(instrument, side, now)
      - write_to_state_for_opposite(state, instrument, inventory_sign, now)
    """
    def __init__(self, poisson: Optional[RollingPoissonCalibrator] = None, ewma: Optional[EWMACalibrator] = None):
        self.poisson = poisson or RollingPoissonCalibrator()
        self.ewma = ewma or EWMACalibrator()

    def update(self, event: FlowAtom):
        self.poisson.update(event)
        self.ewma.update(event)

    def get_lambda(self, instrument: str, side: int, now: Optional[pd.Timestamp] = None) -> float:
        lam_p = self.poisson.get_lambda_per_min(instrument, side, now)
        if lam_p is not None:
            return lam_p
        return self.ewma.get_lambda_per_min(instrument, side, now)

    def write_to_state_for_opposite(self, state: Dict[str, Any], instrument: str, inventory_sign: int, now: Optional[pd.Timestamp] = None):
        """
        Given current inventory sign (+1 long, -1 short), we care about the arrival rate of
        opposite client flow that would offset our risk.

        If we are long (inv>0), we want future clients who BUY from us (side=+1) or SELL? 
        Convention: FlowEvent.side = +1 means client buys from us -> we sell -> inventory decreases.
        When we are LONG, to reduce long, we want to SELL to clients (i.e., clients BUY from us): side=+1.
        When we are SHORT, to reduce short, we want to BUY from clients (i.e., clients SELL to us): side=-1.
        """
        desired_side = +1 if inventory_sign > 0 else -1
        lam = self.get_lambda(instrument, desired_side, now)
        d = state.setdefault("lambda_per_minute", {})
        d[instrument] = lam

# ---- Adapter snippet you can use inside your event loop ----
# lm = LambdaManager(RollingPoissonCalibrator(15), EWMACalibrator(half_life_minutes=10))
# for each client event:
#    lm.update( FlowAtom(ts=event.ts, instrument=event.instrument, side=event.side, qty=event.qty) )
#    inv = state["inventory"][event.instrument]
#    inv_sign = 1 if inv>0 else (-1 if inv<0 else 0)
#    if inv_sign != 0:
#        lm.write_to_state_for_opposite(state, event.instrument, inv_sign, now=event.ts)
