"""
perbaiki_titik_repair.py
Perbaiki titik yang tidak sesuai (flag_repair = 1) dengan memindahkannya
KE DALAM poligon Final_SLS yang sesuai.

Yang dimaksud "poligon yang sesuai" = poligon pada Final_SLS_202516105.geojson
yang idsubsls-nya sama dengan kolom level_6_full_code pada titik tersebut.

Untuk setiap titik flag_repair = 1:
  - jika sudah berada di dalam poligon target  -> tidak digeser (status SUDAH_SESUAI)
  - jika di luar poligon target               -> digeser ke titik terdekat yang
                                                  masih di dalam poligon (DIPINDAHKAN)
  - jika kode target tidak ada di Final_SLS   -> dibiarkan (POLIGON_TIDAK_DITEMUKAN)

Hasil:
  - GPKG  : layer baru berisi titik yang sudah diperbaiki
  - CSV   : ringkasan kode lama -> kode target + status tiap titik

Cara pakai:
    python perbaiki_titik_repair.py
    python perbaiki_titik_repair.py --input hasil_identifikasi_titik.gpkg \
        --out-gpkg hasil_identifikasi_titik_repaired.gpkg --out-csv ringkasan_repair.csv
"""

import argparse
import json
import math

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

GPKG_IN = "hasil_identifikasi_titik.gpkg"
LAYER_IN = "hasil_identifikasi_titik"
SERIES = "Final_SLS_202516105.geojson"
GPKG_OUT = "hasil_identifikasi_titik_repaired.gpkg"
LAYER_OUT = "hasil_identifikasi_titik_repaired"
CSV_OUT = "ringkasan_repair.csv"

# kolom yang dipertahankan pada CSV ringkasan
SUMMARY_COLS = [
    "id_assignment", "kode_lama", "kode_geometris_asli", "kode_target",
    "status_repair", "jarak_geser_m",
    "target_kdkec", "target_nmkec", "target_kddesa", "target_nmdesa",
    "target_idsls", "target_nmsls",
    "latitude_origin", "longitude_origin", "longitude_baru", "latitude_baru",
]


# --------------------------------------------------------------------------
# util
# --------------------------------------------------------------------------
def make_valid(geom):
    try:
        from shapely import make_valid as _mv
        if not geom.is_valid:
            return _mv(geom)
    except Exception:  # noqa: BLE001
        try:
            from shapely.validation import make_valid as _mv2
            if not geom.is_valid:
                return _mv2(geom)
        except Exception:  # noqa: BLE001
            pass
    return geom


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def closest_point_inside(pt, poly):
    """Titik terdekat dari pt yang berada di dalam poly."""
    if poly.contains(pt):
        return pt
    # titik terdekat pada batas poligon
    near = nearest_points(pt, poly.boundary)[1]
    # titik jaminan di dalam
    interior = poly.representative_point()
    # geser dari batas menuju titik dalam, sedikit demi sedikit
    for t in (1e-5, 1e-4, 1e-3, 0.01, 0.1, 0.5, 1.0):
        cand = Point(
            near.x + (interior.x - near.x) * t,
            near.y + (interior.y - near.y) * t,
        )
        if poly.contains(cand):
            return cand
    return interior


# --------------------------------------------------------------------------
# muat data
# --------------------------------------------------------------------------
def load_polygons(path=SERIES):
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    polys = {}
    for feat in gj["features"]:
        p = feat["properties"]
        code = str(p.get("idsubsls") or "").strip()
        if not code:
            continue
        polys[code] = {
            "geometry": make_valid(shape(feat["geometry"])),
            "kdkec": p.get("kdkec"),
            "nmkec": p.get("nmkec"),
            "kddesa": p.get("kddesa"),
            "nmdesa": p.get("nmdesa"),
            "idsls": p.get("idsls"),
            "nmsls": p.get("nmsls"),
        }
    return polys


def main():
    ap = argparse.ArgumentParser(description="Perbaiki titik flag_repair=1 masuk ke poligon Final_SLS")
    ap.add_argument("--input", default=GPKG_IN)
    ap.add_argument("--layer", default=LAYER_IN)
    ap.add_argument("--out-gpkg", default=GPKG_OUT)
    ap.add_argument("--out-csv", default=CSV_OUT)
    args = ap.parse_args()

    print(f"[1/4] baca titik flag_repair=1 dari {args.input} ...")
    g = gpd.read_file(args.input, layer=args.layer, where="flag_repair = 1")
    if g.crs is None:
        g = g.set_crs("EPSG:4326")
    print(f"      {len(g)} titik")

    print(f"[2/4] muat poligon {SERIES} ...")
    polys = load_polygons()
    print(f"      {len(polys)} polygon")

    print("[3/4] proses geser tiap titik ...")
    moved = []
    statuses = []
    jarak = []
    kode_target_list = []
    new_geoms = []
    counts = {"SUDAH_SESUAI": 0, "DIPINDAHKAN": 0, "POLIGON_TIDAK_DITEMUKAN": 0, "KOORDINAT_INVALID": 0}

    for row in g.itertuples():
        pt = row.geometry
        kode_target = str(getattr(row, "level_6_full_code") or "").strip()
        kode_geometris = str(getattr(row, "idsubsls") or "").strip()

        # kode target divalidasi dulu
        target = polys.get(kode_target)
        if pt is None or pt.is_empty or not isinstance(pt, Point) or not (-90 <= pt.y <= 90):
            status = "KOORDINAT_INVALID"
            new_pt = pt
        elif target is None:
            status = "POLIGON_TIDAK_DITEMUKAN"
            new_pt = pt
        else:
            poly = target["geometry"]
            if poly.contains(pt) or poly.covers(pt):
                status = "SUDAH_SESUAI"
                new_pt = pt
            else:
                new_pt = closest_point_inside(pt, poly)
                status = "DIPINDAHKAN"

        d = 0.0
        if new_pt is not None and pt is not None and isinstance(pt, Point):
            d = haversine_m(pt.y, pt.x, new_pt.y, new_pt.x)

        new_geoms.append(new_pt)
        statuses.append(status)
        jarak.append(round(d, 2))
        kode_target_list.append(kode_target)
        counts[status] = counts.get(status, 0) + 1

    out = g.copy()
    out["kode_lama"] = out["level_6_full_code"]
    out["kode_geometris_asli"] = out["idsubsls"]
    out["kode_target"] = kode_target_list
    out["status_repair"] = statuses
    out["jarak_geser_m"] = jarak
    out["longitude_origin"] = g.geometry.x
    out["latitude_origin"] = g.geometry.y
    out = out.set_geometry(gpd.GeoSeries(new_geoms, index=out.index, crs="EPSG:4326"))
    out["longitude_baru"] = out.geometry.x
    out["latitude_baru"] = out.geometry.y

    # kolom nama wilayah target
    for col, key in [
        ("target_kdkec", "kdkec"), ("target_nmkec", "nmkec"),
        ("target_kddesa", "kddesa"), ("target_nmdesa", "nmdesa"),
        ("target_idsls", "idsls"), ("target_nmsls", "nmsls"),
    ]:
        out[col] = [polys[c][key] if c in polys else None for c in kode_target_list]

    print("[4/4] tulis hasil ...")
    if args.out_gpkg:
        out.to_file(args.out_gpkg, layer=LAYER_OUT, driver="GPKG")
        print(f"      GPKG : {args.out_gpkg} (layer {LAYER_OUT})")
    summary = out[[c for c in SUMMARY_COLS if c in out.columns]]
    summary.to_csv(args.out_csv, index=False, encoding="utf-8-sig")
    print(f"      CSV  : {args.out_csv}")

    print("\n== RINGKASAN ==")
    for k, v in counts.items():
        print(f"  {k:<24}: {v}")
    print(f"  TOTAL                   : {len(out)}")
    if counts.get("DIPINDAHKAN"):
        dd = out.loc[out["status_repair"] == "DIPINDAHKAN", "jarak_geser_m"]
        print(f"\n  jarak geser: min={dd.min():.2f} m  median={dd.median():.2f} m  maks={dd.max():.2f} m")


if __name__ == "__main__":
    main()
