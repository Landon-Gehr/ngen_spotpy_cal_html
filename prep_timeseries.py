#!/usr/bin/env python3
"""Convert data/observed + data/simulated CSVs into:
     data/bin/gage-<id>.bin   (compact binary, see format below)
     data/clim.json           (monthly climatology from the FULL raw records, m^3/s)

Binary format (little-endian): float64 start_ms(UTC) | int32 n | int32 pad |
  float32 obs[n] | float32 sim[n]   on a shared 15-min grid (overlap of both
  records; NaN where a value is missing).  Timestamps are treated as UTC.

Usage:  python3 prep_timeseries.py [--data data]
Needs:  pip install pandas numpy
"""
import argparse, json, struct
from pathlib import Path
import numpy as np
import pandas as pd


def load(path, tcol, vcol):
    df = pd.read_csv(path, usecols=[tcol, vcol])
    t = pd.to_datetime(df[tcol], errors="coerce", utc=True)
    v = pd.to_numeric(df[vcol], errors="coerce")
    ok = (t.notna() & np.isfinite(v)).to_numpy()
    return pd.Series(v.to_numpy()[ok], index=t[ok].dt.tz_convert(None)).sort_index()


def monthly(s):
    m = s.groupby(s.index.month).mean().reindex(range(1, 13))
    return [None if pd.isna(x) else float(x) for x in m]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    d = Path(ap.parse_args().data)
    (d / "bin").mkdir(parents=True, exist_ok=True)
    clim = {}
    for op in sorted((d / "observed").glob("*.csv")):
        sp = d / "simulated" / op.name
        if not sp.exists():
            print("skip (no simulated file):", op.name)
            continue
        gage = op.stem.removeprefix("gage-")
        o = load(op, "value_date", "obs_flow")
        s = load(sp, "timestamp", "flow_m3s")
        if o.empty or s.empty:
            print("skip (empty):", op.name)
            continue
        clim[gage] = {"obs": monthly(o), "sim": monthly(s)}
        o15 = o.groupby(o.index.round("15min")).mean()
        s15 = s.groupby(s.index.round("15min")).mean()
        start = max(o15.index[0], s15.index[0])
        end = min(o15.index[-1], s15.index[-1])
        if end < start:
            print("skip (records do not overlap):", op.name)
            continue
        idx = pd.date_range(start, end, freq="15min")
        O = o15.reindex(idx).to_numpy("float32")
        S = s15.reindex(idx).to_numpy("float32")
        start_ms = (idx[0] - pd.Timestamp("1970-01-01")) // pd.Timedelta("1ms")
        with open(d / "bin" / f"gage-{gage}.bin", "wb") as f:
            f.write(struct.pack("<dii", float(start_ms), len(idx), 0))
            f.write(O.astype("<f4").tobytes())
            f.write(S.astype("<f4").tobytes())
        print(f"gage {gage}: {len(idx)} steps, {idx[0]} -> {idx[-1]}")
    (d / "clim.json").write_text(json.dumps(clim, separators=(",", ":")))
    print("wrote", d / "clim.json")


if __name__ == "__main__":
    main()
