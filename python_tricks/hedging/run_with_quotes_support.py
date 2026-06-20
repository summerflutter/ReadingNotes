
import pandas as pd
from typing import Optional, Any
import importlib.util

#spec = importlib.util.spec_from_file_location('internalization_backtest', '/mnt/data/internalization_backtest.py')
spec = importlib.util.spec_from_file_location('internalization_backtest', 'internalization_backtest.py')
ib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ib)

def run_backtest_with_quotes(flow_df: pd.DataFrame, price_df: pd.DataFrame, strategy, cfg: Optional[Any] = None):
    if cfg is None:
        cfg = ib.BacktestConfig(instruments=sorted(price_df['instrument'].unique().tolist()))
    sim = ib.InternalizationSimulator(cfg, strategy)

    grouped_prices = price_df.groupby('ts')
    grouped_flows = flow_df.groupby('ts')

    all_ts = sorted(set(price_df['ts']).union(set(flow_df['ts'])))

    for ts in all_ts:
        if ts in grouped_prices.indices:
            dfp = grouped_prices.get_group(ts)
            for row in dfp.itertuples(index=False):
                sim.state.setdefault('last_mid', {})[row.instrument] = row.mid
        sim.on_time(ts)
        if ts in grouped_flows.indices:
            for row in grouped_flows.get_group(ts).itertuples(index=False):
                ev = ib.FlowEvent(ts=row.ts, instrument=row.instrument, side=row.side, qty=row.qty, px=row.px, mid=row.mid, client_id=row.client_id)
                sim.on_client_event(ev)
                sim.on_time(ts)
    if all_ts:
        sim.on_time(all_ts[-1] + pd.Timedelta(minutes=1))
    return sim.results()
