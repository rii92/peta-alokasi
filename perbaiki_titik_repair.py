"""
perbaiki_titik_repair.py
Perbaiki titik yang tidak sesuai (flag_repair = 1) dengan memindahkannya
KE DALAM poligon Final_SLS yang sesuai.

Yang dimaksud "poligon yang sesuai" = poligon pada Final_SLS_202516105.geojson
yang idsubsls-nya sama dengan kolom level_6_full_code pada titik tersebut.

Aturan:
  - flag_repair = 0 : titik sudah benar, TIDAK dipindah (status TIDAK_DIPINDAH)
  - flag_repair = 1 : diperbaiki:
        * sudah di dalam poligon target -> tidak digeser (SUDAH_SESUAI)
        * di luar poligon target        -> digeser ke titik terdekat yang masih
                                           di dalam poligon (DIPINDAHKAN)
        * kode target tidak ada di SLS  -> dibiarkan (POLIGON_TIDAK_DITEMUKAN)

Hasil:
  - GPKG  : layer baru berisi titik (flag_repair=0 tetap, flag_repair=1 diperbaiki)
  - CSV   : ringkasan kode lama -> kode target + status tiap titik

Cara pakai:
    python perbaiki_titik_repair.py                       # semua titik
    python perbaiki_titik_repair.py --only-repair         # hanya flag_repair=1
    python perbaiki_titik_repair.py --input hasil_identifikasi_titik.gpkg \
        --out-gpkg hasil_identifikasi_titik_repaired.gpkg --out-csv ringkasan_repair.csv
"""

import argparse
import json
import math
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

GPKG_IN = "hasil_identifikasi_titik.gpkg"
LAYER_IN = "hasil_identifikasi_titik"
SERIES = "Final_SLS_202516105.geojson"
GPKG_OUT = "hasil_identifikasi_titik_repaired.gpkg"
LAYER_OUT = "hasil_identifikasi_titik_repaired"
CSV_OUT = "ringkasan_repair.csv"


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


def pick_col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def main():
    ap = argparse.ArgumentParser(description="Perbaiki titik flag_repair=1 masuk ke poligon Final_SLS")
    ap.add_argument("--input", default=GPKG_IN)
    ap.add_argument("--layer", default=LAYER_IN)
    ap.add_argument("--out-gpkg", default=GPKG_OUT)
    ap.add_argument("--layer-out", default=None,
                    help="nama layer output (default: nama file gpkg tanpa ekstensi)")
    ap.add_argument("--out-csv", default=CSV_OUT)
    ap.add_argument("--only-repair", action="store_true",
                    help="hanya proses flag_repair=1 (default: semua titik, flag_repair=0 dibiarkan)")
    args = ap.parse_args()

    where = "flag_repair = 1" if args.only_repair else None
    print(f"[1/4] baca titik dari {args.input}" + (" (hanya flag_repair=1)" if where else " (semua titik)") + " ...")
    g = gpd.read_file(args.input, layer=args.layer, where=where)
    if g.crs is None:
        g = g.set_crs("EPSG:4326")
    print(f"      {len(g)} titik")

    # deteksi nama kolom (berbeda antar file)
    id_col = pick_col(g, "id_assignment", "assignment_id")
    subsls_col = pick_col(g, "idsubsls", "idsubsls_origin", "idsubsls_asli")
    code_col = pick_col(g, "level_6_full_code", "level6fullcode")
    flag_col = pick_col(g, "flag_repair")
    if code_col is None:
        raise SystemExit(f"Kolom kode target (level_6_full_code) tidak ditemukan. Kolom: {list(g.columns)}")
    if flag_col is None:
        raise SystemExit(f"Kolom flag_repair tidak ditemukan. Kolom: {list(g.columns)}")
    print(f"      kolom -> id={id_col} | subsls={subsls_col} | kode={code_col} | flag={flag_col}")

    print(f"[2/4] muat poligon {SERIES} ...")
    polys = load_polygons()
    print(f"      {len(polys)} polygon")

    print("[3/4] proses tiap titik ...")
    statuses = []
    jarak = []
    kode_target_list = []
    new_geoms = []
    counts = {
        "TIDAK_DIPINDAH": 0, "SUDAH_SESUAI": 0, "DIPINDAHKAN": 0,
        "POLIGON_TIDAK_DITEMUKAN": 0, "KOORDINAT_INVALID": 0,
    }

    for row in g.itertuples():
        pt = row.geometry
        kode_target = str(getattr(row, code_col) or "").strip()
        flag = int(getattr(row, flag_col, 0) or 0)

        # flag_repair=0 -> titik sudah benar, JANGAN dipindah
        if flag == 0:
            status = "TIDAK_DIPINDAH"
            new_pt = pt
        # kode target divalidasi dulu
        elif pt is None or pt.is_empty or not isinstance(pt, Point) or not (-90 <= pt.y <= 90):
            status = "KOORDINAT_INVALID"
            new_pt = pt
        elif polys.get(kode_target) is None:
            status = "POLIGON_TIDAK_DITEMUKAN"
            new_pt = pt
        else:
            poly = polys[kode_target]["geometry"]
            if poly.contains(pt) or poly.covers(pt):
                status = "SUDAH_SESUAI"
                new_pt = pt
            else:
                new_pt = closest_point_inside(pt, poly)
                status = "DIPINDAHKAN"

        d = 0.0
        if new_pt is not None and pt is not None and isinstance(pt, Point) and isinstance(new_pt, Point):
            d = haversine_m(pt.y, pt.x, new_pt.y, new_pt.x)

        new_geoms.append(new_pt)
        statuses.append(status)
        jarak.append(round(d, 2))
        kode_target_list.append(kode_target)
        counts[status] = counts.get(status, 0) + 1

    out = g.copy()
    out["kode_lama"] = out[code_col]
    if subsls_col:
        out["kode_geometris_asli"] = out[subsls_col]
    out["kode_target"] = kode_target_list
    out["status_repair"] = statuses
    out["jarak_geser_m"] = jarak
    if "longitude_origin" not in out.columns:
        out["longitude_origin"] = g.geometry.x
    if "latitude_origin" not in out.columns:
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
    layer_out = args.layer_out or Path(args.out_gpkg).stem
    if args.out_gpkg:
        out.to_file(args.out_gpkg, layer=layer_out, driver="GPKG")
        print(f"      GPKG : {args.out_gpkg} (layer {layer_out})")
    summary_cols = [
        id_col, "kode_lama", "kode_geometris_asli", "kode_target",
        "status_repair", "jarak_geser_m",
        "target_kdkec", "target_nmkec", "target_kddesa", "target_nmdesa",
        "target_idsls", "target_nmsls",
        "latitude_origin", "longitude_origin", "longitude_baru", "latitude_baru",
    ]
    summary = out[[c for c in summary_cols if c in out.columns]]
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
