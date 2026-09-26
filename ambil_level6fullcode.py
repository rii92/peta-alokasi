"""
ambil_level6fullcode.py
Ambil level6fullcode (kode subSLS 16 digit) dari titik koordinat.

Level 6 (subSLS) susunan kode BPS:
    kdprov(2) + kdkab(2) + kdkec(3) + kddesa(3) + kdsls(4) + kdsubsls(2) = 16 digit
    contoh: 61 05 060 005 0007 00 -> 6105060005000700

Cara pakai:
    python ambil_level6fullcode.py 0.425 110.8819            # satu titik, tampil di terminal
    python ambil_level6fullcode.py 0.425 110.8819 -q         # hanya cetak kode
    python ambil_level6fullcode.py 0.425 110.8819 0.36 110.69 # beberapa titik
    python ambil_level6fullcode.py                          # data-assignment bawaan -> csv
    python ambil_level6fullcode.py data-bangunan.xlsx      # file lain (xlsx/csv/tsv)
    python ambil_level6fullcode.py titik.txt               # teks: lat,lon per baris
    python ambil_level6fullcode.py -o hasil.csv            # ganti nama file hasil
    python ambil_level6fullcode.py --no-shapely            # mode pure-python
"""

import sys
import json
import argparse

import pandas as pd

GEOJSON_PATH = "Final_SLS_202516105.geojson"
DEFAULT_INPUT = "data-assignment.xlsx"

# kolom kandidat untuk latitude / longitude
LAT_KEYS = ["latitude", "lat", "Latitude", "y", "lintang"]
LON_KEYS = ["longitude", "lon", "lng", "long", "Longitude", "x", "bujur"]

PROPS = [
    "idsubsls", "idsls", "kdprov", "kdkab", "kdkec", "kddesa", "kdsls", "kdsubsls",
    "nmprov", "nmkab", "nmkec", "nmdesa", "nmsls", "luas",
]


# --------------------------------------------------------------------------
# baca sumber polygon
# --------------------------------------------------------------------------
def load_polygons(path=GEOJSON_PATH):
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    records, geometries = [], []
    for feat in gj.get("features", []):
        props = feat.get("properties") or {}
        rec = {k: props.get(k) for k in PROPS}
        if rec.get("idsubsls") is None:
            rec["idsubsls"] = rec.get("idsls")
        records.append(rec)
        geometries.append(feat["geometry"])
    return records, geometries


# --------------------------------------------------------------------------
# point in polygon
# --------------------------------------------------------------------------
def _point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        if (y1 > y) != (y2 > y):
            xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xint:
                inside = not inside
    return inside


def _point_in_polygon(x, y, polygon):
    """polygon = list of rings; ring pertama = exterior, lainnya = hole."""
    if not _point_in_ring(x, y, polygon[0]):
        return False
    for hole in polygon[1:]:
        if _point_in_ring(x, y, hole):
            return False
    return True


def _coords_to_polygons(geom):
    """rflatten GeoJSON Polygon/MultiPolygon jadi list of polygon (list of ring)."""
    t = geom.get("type")
    c = geom.get("coordinates") or []
    if t == "Polygon":
        return [c]
    if t == "MultiPolygon":
        return c
    return []


class LocatorPurePython:
    """Fallback tanpa shapely: pindai semua polygon."""

    name = "pure-python"

    def __init__(self, records, geometries):
        self.items = []
        for rec, geom in zip(records, geometries):
            for poly in _coords_to_polygons(geom):
                if not poly or not poly[0]:
                    continue
                xs, ys = [], []
                for ring in poly:
                    for pt in ring:
                        xs.append(pt[0])
                        ys.append(pt[1])
                if not xs:
                    continue
                self.items.append(
                    (rec, poly, (min(xs), min(ys), max(xs), max(ys)))
                )

    def find(self, lat, lon):
        for rec, poly, (minx, miny, maxx, maxy) in self.items:
            if not (minx <= lon <= maxx and miny <= lat <= maxy):
                continue
            if _point_in_polygon(lon, lat, poly):
                return rec
        return None


class LocatorShapely:
    """Cepat: STRtree + prepared geometry."""

    name = "shapely"

    def __init__(self, records, geometries):
        from shapely.geometry import shape
        from shapely.prepared import prep
        from shapely.strtree import STRtree

        self.records = records
        self.geoms = [shape(g) for g in geometries]
        self.prepared = [prep(g) for g in self.geoms]
        self.tree = STRtree(self.geoms)

    def find(self, lat, lon):
        from shapely.geometry import Point

        pt = Point(lon, lat)
        for idx in self.tree.query(pt):
            if self.prepared[idx].contains(pt):
                return self.records[idx]
        return None


def build_locator(records, geometries, prefer_shapely=True):
    if prefer_shapely:
        try:
            return LocatorShapely(records, geometries)
        except Exception as exc:  # noqa: BLE001
            print(f"[info] shapely tidak bisa dipakai ({exc}), memakai mode pure-python.")
    return LocatorPurePython(records, geometries)


# --------------------------------------------------------------------------
# baca titik
# --------------------------------------------------------------------------
def read_table(path):
    lower = path.lower()
    if lower.endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(path)
        except Exception:  # noqa: BLE001
            return pd.read_csv(path, sep="\t")
    if lower.endswith((".tsv", ".txt")):
        return pd.read_csv(path, sep="\t")
    # .xlsx hasil ekspor BPS kadang sebenarnya TSV
    try:
        return pd.read_excel(path)
    except Exception:  # noqa: BLE001
        try:
            return pd.read_csv(path, sep="\t")
        except Exception:  # noqa: BLE001
            return pd.read_csv(path)


def pick_column(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    low = {str(c).strip().lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    return None


def read_points(path=None):
    """Kembalikan (df, lat_col, lon_col)."""
    if path is None:
        df = read_table(DEFAULT_INPUT)
    else:
        df = read_table(path)

    lat_col = pick_column(df, LAT_KEYS)
    lon_col = pick_column(df, LON_KEYS)

    # file teks tanpa header: "lat<tab>lon" per baris
    if (lat_col is None or lon_col is None) and path and path.lower().endswith((".txt", ".csv")):
        raw = pd.read_csv(
            path, sep=None, engine="python", header=None,
            names=["latitude", "longitude"], comment="#",
        )
        raw = raw.apply(pd.to_numeric, errors="coerce").dropna(how="all")
        print(f"[info] dibaca sebagai file teks tanpa header ({len(raw)} baris)")
        return raw, "latitude", "longitude"

    if lat_col is None or lon_col is None:
        raise SystemExit(
            f"Kolom latitude/longitude tidak ditemukan. Kolom tersedia: {list(df.columns)}"
        )
    return df, lat_col, lon_col


# --------------------------------------------------------------------------
# proses
# --------------------------------------------------------------------------
def enrich(df, lat_col, lon_col, locator, prefix=""):
    lat = pd.to_numeric(df[lat_col], errors="coerce")
    lon = pd.to_numeric(df[lon_col], errors="coerce")

    out_cols = [
        "level6fullcode", "level6kode_provinsi", "level6kode_kabupaten",
        "level6kode_kecamatan", "level6kode_desa", "level6kode_sls", "level6kode_subsls",
        "level6nama_provinsi", "level6nama_kabupaten", "level6nama_kecamatan",
        "level6nama_desa", "level6nama_sls", "level6luas",
    ]
    for c in out_cols:
        df[c] = None

    unmatched = 0
    cache = {}
    for i, (lat_v, lon_v) in enumerate(zip(lat, lon)):
        if pd.isna(lat_v) or pd.isna(lon_v):
            continue
        key = (round(float(lat_v), 7), round(float(lon_v), 7))
        if key not in cache:
            cache[key] = locator.find(float(lat_v), float(lon_v))
        rec = cache[key]
        if rec is None:
            unmatched += 1
            continue
        df.iat[i, df.columns.get_loc("level6fullcode")] = str(rec.get("idsubsls") or "")
        df.iat[i, df.columns.get_loc("level6kode_provinsi")] = str(rec.get("kdprov") or "")
        df.iat[i, df.columns.get_loc("level6kode_kabupaten")] = str(rec.get("kdkab") or "")
        df.iat[i, df.columns.get_loc("level6kode_kecamatan")] = str(rec.get("kdkec") or "")
        df.iat[i, df.columns.get_loc("level6kode_desa")] = str(rec.get("kddesa") or "")
        df.iat[i, df.columns.get_loc("level6kode_sls")] = str(rec.get("kdsls") or "")
        df.iat[i, df.columns.get_loc("level6kode_subsls")] = str(rec.get("kdsubsls") or "")
        df.iat[i, df.columns.get_loc("level6nama_provinsi")] = rec.get("nmprov")
        df.iat[i, df.columns.get_loc("level6nama_kabupaten")] = rec.get("nmkab")
        df.iat[i, df.columns.get_loc("level6nama_kecamatan")] = rec.get("nmkec")
        df.iat[i, df.columns.get_loc("level6nama_desa")] = rec.get("nmdesa")
        df.iat[i, df.columns.get_loc("level6nama_sls")] = rec.get("nmsls")
        df.iat[i, df.columns.get_loc("level6luas")] = rec.get("luas")

    df["level6fullcode"] = df["level6fullcode"].fillna("").astype(str).str.strip()
    total_valid = int((lat.notna() & lon.notna()).sum())
    print(
        f"[info] locator={locator.name} | titik valid={total_valid} | "
        f"cocok={total_valid - unmatched} | tidak cocok={unmatched}"
    )
    return df


def print_single(lat, lon, locator):
    """Cetak level6fullcode untuk satu titik ke terminal."""
    rec = locator.find(lat, lon)
    print("=" * 52)
    print(f"Latitude   : {lat}")
    print(f"Longitude  : {lon}")
    print("-" * 52)
    if rec is None:
        print("level6fullcode : TIDAK DITEMUKAN")
        print("Titik ini berada di luar area Sanggau / tidak ada polygon yang memuat.")
        print("=" * 52)
        return

    print(f"level6fullcode : {rec.get('idsubsls')}")
    print("-" * 52)
    print(f"  kdprov  ({rec.get('kdprov')}) : {rec.get('nmprov')}")
    print(f"  kdkab   ({rec.get('kdkab')}) : {rec.get('nmkab')}")
    print(f"  kdkec   ({rec.get('kdkec')}) : {rec.get('nmkec')}")
    print(f"  kddesa  ({rec.get('kddesa')}) : {rec.get('nmdesa')}")
    print(f"  kdsls   ({rec.get('kdsls')}) : {rec.get('nmsls')}")
    print(f"  kdsubsls({rec.get('kdsubsls')})")
    print("=" * 52)


def main():
    ap = argparse.ArgumentParser(
        description="Ambil level6fullcode dari titik koordinat",
        epilog=(
            "contoh:\n"
            "  python ambil_level6fullcode.py 0.425 110.8819\n"
            "  python ambil_level6fullcode.py 0.425 110.8819 0.363 110.697\n"
            "  python ambil_level6fullcode.py data-bangunan.xlsx -o hasil.csv"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "input", nargs="*",
        help="koordinat (lat lon ...) atau nama file titik. Kosong = data-assignment bawaan",
    )
    ap.add_argument("-o", "--output", default="titik_level6fullcode.csv", help="file hasil (mode file)")
    ap.add_argument("--no-shapely", action="store_true", help="paksa mode pure-python")
    ap.add_argument("-q", "--quiet", action="store_true", help="hanya cetak kode, tanpa keterangan")
    args = ap.parse_args()

    # mode koordinat langsung: semua argumen positional berupa angka
    coords = []
    for token in args.input:
        try:
            coords.append(float(token))
        except ValueError:
            coords = []
            break

    is_coord_mode = len(coords) >= 2 and len(coords) % 2 == 0

    if len(args.input) == 1 and len(coords) == 1:
        raise SystemExit(
            f"Koordinat harus berpasangan (latitude lalu longitude).\n"
            f"Contoh: python ambil_level6fullcode.py {args.input[0]} 110.8819"
        )

    records, geometries = load_polygons()
    if not is_coord_mode:
        print(f"[info] polygon dimuat: {len(records)}")
    locator = build_locator(records, geometries, prefer_shapely=not args.no_shapely)

    # ---- mode koordinat langsung ----
    if is_coord_mode:
        pairs = list(zip(coords[0::2], coords[1::2]))
        if args.quiet:
            for lat, lon in pairs:
                rec = locator.find(lat, lon)
                print(rec.get("idsubsls") if rec else "TIDAK_DITEMUKAN")
        else:
            for n, (lat, lon) in enumerate(pairs, 1):
                if len(pairs) > 1:
                    print(f"\n### Titik {n} dari {len(pairs)}")
                print_single(lat, lon, locator)
        return

    # ---- mode file ----
    file_arg = args.input[0] if args.input else None
    if args.input and len(coords) == len(args.input) and len(args.input) > 1:
        raise SystemExit(
            f"Jumlah koordinat harus genap (latitude lalu longitude), "
            f"tapi ada {len(args.input)} angka.\n"
            f"Contoh: python ambil_level6fullcode.py {args.input[0]} {args.input[1]}"
        )
    if args.input and len(args.input) > 1:
        raise SystemExit(
            f"Argumen tidak dikenali: {args.input[1:]}\n"
            "Gunakan pasangan angka (lat lon), atau satu nama file."
        )

    df, lat_col, lon_col = read_points(file_arg)
    print(f"[info] titik dimuat: {len(df)} baris dari {file_arg or DEFAULT_INPUT}")

    out = enrich(df, lat_col, lon_col, locator)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"[info] hasil disimpan: {args.output}")

    found = out[out["level6fullcode"].astype(str).str.strip() != ""]
    if len(found):
        print("\n[contoh 5 baris]")
        cols = [
            c for c in ["latitude", "longitude", "level6fullcode", "level6nama_desa", "level6nama_sls"]
            if c in found.columns
        ]
        print(found[cols].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
