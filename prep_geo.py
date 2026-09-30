#!/usr/bin/env python3
"""Simplify each gpkgs/gage-<id>.gpkg (layers: divides, flowpaths, nexus), reproject to
EPSG:4326 and write a compact geo/gage-<id>.json that the web app loads directly.
Optionally also saves simplified GPKG copies (--gpkg-out) that you can open in QGIS.

Usage:
  python3 prep_geo.py --gpkgs gpkgs --out geo --div-tol 50 --flow-tol 10 [--gpkg-out gpkgs_simplified]
Tolerances are in metres (0 = no simplification). Flowpath hover targets are the
vertices, so keep --flow-tol small (or 0) if you want dense hover.
Needs:  pip install geopandas pyogrio shapely
"""
import argparse, json
from pathlib import Path
import geopandas as gpd
from shapely.geometry import mapping

ID_COLS = ["divide_id", "flowpath_id", "nexus_id", "id", "ID", "link", "link_id",
           "feature_id", "comid", "hydrolocation_id"]


def rnd(c):
    if isinstance(c[0], (int, float)):
        return [round(c[0], 5), round(c[1], 5)]
    return [rnd(x) for x in c]


def read(path, name, tol_m):
    try:
        g = gpd.read_file(path, layer=name)
    except Exception:
        return None
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    if g.crs is not None:
        g = g.to_crs(4326)
    if tol_m > 0:
        g["geometry"] = g.geometry.simplify(tol_m / 111320, preserve_topology=True)
    col = next((c for c in ID_COLS if c in g.columns), None)
    g["_id"] = (g[col] if col else g.index).astype(str)
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpkgs", default="gpkgs")
    ap.add_argument("--out", default="geo")
    ap.add_argument("--div-tol", type=float, default=50)
    ap.add_argument("--flow-tol", type=float, default=10)
    ap.add_argument("--gpkg-out", default=None)
    a = ap.parse_args()
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.gpkg_out:
        Path(a.gpkg_out).mkdir(parents=True, exist_ok=True)

    for p in sorted(Path(a.gpkgs).glob("*.gpkg")):
        L = {n: read(p, n, t) for n, t in
             (("divides", a.div_tol), ("flowpaths", a.flow_tol), ("nexus", 0))}
        out = {}
        d, f, n = L["divides"], L["flowpaths"], L["nexus"]
        if d is not None:
            out["divides"] = {"type": "FeatureCollection", "features": [
                {"type": "Feature", "properties": {"id": i},
                 "geometry": {"type": m["type"], "coordinates": rnd(m["coordinates"])}}
                for i, m in zip(d["_id"], (mapping(x) for x in d.geometry))]}
        if f is not None:
            out["flowpaths"] = [
                [i, [rnd(list(l.coords)) for l in (g.geoms if g.geom_type == "MultiLineString" else [g])]]
                for i, g in zip(f["_id"], f.geometry)]
        if n is not None:
            out["nexus"] = [[i, round(g.x, 5), round(g.y, 5)] for i, g in zip(n["_id"], n.geometry)]
        dest = out_dir / f"{p.stem}.json"
        dest.write_text(json.dumps(out, separators=(",", ":")))
        print(f"{p.name}: {p.stat().st_size/1e3:.0f} KB -> {dest.stat().st_size/1e3:.0f} KB")
        if a.gpkg_out:
            for name, g in L.items():
                if g is not None:
                    g.drop(columns="_id").to_file(Path(a.gpkg_out) / p.name, layer=name, driver="GPKG")


if __name__ == "__main__":
    main()
