import streamlit as st
import pandas as pd
import folium
from folium import DivIcon
from folium.plugins import MarkerCluster
import json

st.set_page_config(page_title="Peta Wilayah Tugas Mitra - Sanggau", layout="wide")

GEOJSON_PATH = "Final_SLS_202516105.geojson"
EXCEL_PATH = "data-alokasi-petugas.xlsx"
CMAP = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
    "#469990", "#dcbeff", "#9A6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9",
    "#e6beff", "#1ce6ff", "#ff34ff", "#ff4a46", "#008941",
]


def flatten_coords(coords):
    pts = []
    for item in coords:
        if isinstance(item[0], (int, float)):
            pts.append(item[:2])
        else:
            pts.extend(flatten_coords(item))
    return pts


def centroid_from_coords(coords):
    pts = flatten_coords(coords)
    if not pts:
        return 0.0, 0.0
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


@st.cache_data
def load_data():
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        geojson = json.load(f)
    xl = pd.read_excel(EXCEL_PATH)
    xl["idsubsls"] = xl["idsubsls"].astype(str).str.strip()
    alloc = xl[["idsubsls", "PPL Baru", "PML Baru", "PJ KUDA", "nama_ketua"]].drop_duplicates(subset="idsubsls")
    alloc_map = alloc.set_index("idsubsls").to_dict("index")
    features = []
    for feat in geojson["features"]:
        sid = str(feat["properties"]["idsubsls"]).strip()
        if sid not in alloc_map:
            continue
        props = feat["properties"].copy()
        props.update(alloc_map[sid])
        clat, clon = centroid_from_coords(feat["geometry"]["coordinates"])
        props["centroid_lat"] = clat
        props["centroid_lon"] = clon
        props["luas"] = float(props.get("luas") or 0)
        features.append({"type": "Feature", "properties": props, "geometry": feat["geometry"]})
    all_lats = [f["properties"]["centroid_lat"] for f in features]
    all_lons = [f["properties"]["centroid_lon"] for f in features]
    map_lat = sum(all_lats) / len(all_lats) if all_lats else 0
    map_lon = sum(all_lons) / len(all_lons) if all_lons else 0
    return features, map_lat, map_lon


def build_map(map_lat, map_lon, features, colormap, show_label):
    m = folium.Map(location=[map_lat, map_lon], zoom_start=11, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satelit (Esri World Imagery)", overlay=False,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Jalan (Esri Transport)", overlay=True, opacity=0.7,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Labels (Esri)", overlay=True, opacity=0.7,
    ).add_to(m)

    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    tooltip_fields = ["PPL Baru", "PML Baru", "PJ KUDA", "nama_ketua", "nmsls", "nmdesa", "nmkec", "idsubsls", "luas"]
    tooltip_aliases = ["PPL:", "PML:", "PJ Kuda:", "Ketua SLS:", "Nama SLS:", "Desa:", "Kecamatan:", "ID SubSLS:", "Luas (ha):"]
    tooltip_style = "background-color:white;border:2px solid #333;border-radius:5px;box-shadow:3px 3px 3px rgba(0,0,0,0.3);font-size:13px;padding:8px;"

    def style_fn(feature):
        ppl = feature["properties"].get("PPL Baru", "")
        return {"fillColor": colormap.get(ppl, "#999999"), "color": "#333333", "weight": 1.2, "fillOpacity": 0.55}

    def highlight_fn(feature):
        return {"fillOpacity": 0.85, "weight": 2.5, "color": "#000000"}

    ppl_unique = sorted(colormap.keys())
    for ppl_name in ppl_unique:
        filtered = [f for f in features if f["properties"]["PPL Baru"] == ppl_name]
        fg = folium.FeatureGroup(name=f"PPL: {ppl_name} ({len(filtered)} subSLS)")
        if filtered:
            fc = {"type": "FeatureCollection", "features": filtered}
            folium.GeoJson(
                fc, style_function=style_fn, highlight_function=highlight_fn,
                tooltip=folium.GeoJsonTooltip(
                    fields=tooltip_fields, aliases=tooltip_aliases,
                    localize=True, sticky=True, style=tooltip_style,
                ),
            ).add_to(fg)
        fg.add_to(m)

    mc = MarkerCluster(name="Titik Pusat SubSLS").add_to(m)
    for feat in features:
        props = feat["properties"]
        ppl = props["PPL Baru"]
        color = colormap.get(ppl, "#999999")
        luas_val = round(props["luas"], 3) if props.get("luas") else "-"
        popup_html = f"""<div style='font-family:Arial;min-width:250px'>
            <b style='font-size:14px;color:{color}'>PPL: {ppl}</b><hr style='margin:4px 0'>
            <b>PML:</b> {props.get('PML Baru','-')}<br><b>PJ Kuda:</b> {props.get('PJ KUDA','-')}<br>
            <b>Ketua SLS:</b> {props.get('nama_ketua','-')}<br><b>SLS:</b> {props.get('nmsls','-')}<br>
            <b>Desa:</b> {props.get('nmdesa','-')}<br><b>Kec:</b> {props.get('nmkec','-')}<br>
            <b>ID:</b> {props.get('idsubsls','-')}<br><b>Luas:</b> {luas_val} ha</div>"""
        folium.CircleMarker(
            location=[props["centroid_lat"], props["centroid_lon"]], radius=4,
            color=color, fill=True, fill_color=color, fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{props.get('nmsls','-')} - {ppl}",
        ).add_to(mc)

    if show_label:
        fg_label = folium.FeatureGroup(name="Label Nama PPL", show=True)
        ppl_agg = {}
        for feat in features:
            p = feat["properties"]
            pn = p["PPL Baru"]
            if pn not in ppl_agg:
                ppl_agg[pn] = {"lats": [], "lons": [], "n": 0}
            ppl_agg[pn]["lats"].append(p["centroid_lat"])
            ppl_agg[pn]["lons"].append(p["centroid_lon"])
            ppl_agg[pn]["n"] += 1
        for pn, v in ppl_agg.items():
            avg_lat = sum(v["lats"]) / len(v["lats"])
            avg_lon = sum(v["lons"]) / len(v["lons"])
            color = colormap.get(pn, "#999999")
            label_html = f"""<div style="
                background-color:{color};color:white;font-weight:bold;font-size:12px;
                padding:3px 8px;border-radius:4px;white-space:nowrap;
                border:2px solid white;box-shadow:1px 1px 3px rgba(0,0,0,0.5);
                font-family:Arial;text-align:center;line-height:1.2;
            ">{pn}<br><span style="font-size:10px;font-weight:normal">({v['n']} subSLS)</span></div>"""
            folium.Marker(
                location=[avg_lat, avg_lon],
                icon=DivIcon(html=label_html, icon_size=(180, 30), icon_anchor=(90, 15)),
            ).add_to(fg_label)
        fg_label.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m.get_root().render()


features_all, map_lat, map_lon = load_data()

ppl_all = sorted(set(f["properties"]["PPL Baru"] for f in features_all))
colormap_ppl = {name: CMAP[i % len(CMAP)] for i, name in enumerate(ppl_all)}

st.title("Peta Wilayah Tugas PPL, PML & PJ Kuda - Kab. Sanggau")

st.sidebar.header("Opsi Tampilan")
show_ppl_label = st.sidebar.toggle("Tampilkan Nama PPL di Peta", value=False)

st.sidebar.header("Filter")
filter_level = st.sidebar.radio("Filter berdasarkan:", ["Semua", "Kecamatan", "Desa", "PPL", "PML", "PJ Kuda"])

filtered = features_all

if filter_level == "Kecamatan":
    kec_list = sorted(set(f["properties"]["nmkec"] for f in filtered if f["properties"].get("nmkec")))
    selected_kec = st.sidebar.multiselect("Pilih Kecamatan:", kec_list, default=kec_list[:3])
    filtered = [f for f in filtered if f["properties"].get("nmkec") in selected_kec]
elif filter_level == "Desa":
    kec_list = sorted(set(f["properties"]["nmkec"] for f in features_all if f["properties"].get("nmkec")))
    selected_kec = st.sidebar.selectbox("Pilih Kecamatan:", ["Semua"] + kec_list)
    if selected_kec != "Semua":
        filtered = [f for f in filtered if f["properties"].get("nmkec") == selected_kec]
    desa_list = sorted(set(f["properties"]["nmdesa"] for f in filtered if f["properties"].get("nmdesa")))
    selected_desa = st.sidebar.multiselect("Pilih Desa:", desa_list, default=desa_list[:5])
    filtered = [f for f in filtered if f["properties"].get("nmdesa") in selected_desa]
elif filter_level == "PPL":
    ppl_list = sorted(set(f["properties"]["PPL Baru"] for f in filtered))
    selected_ppl = st.sidebar.multiselect("Pilih PPL:", ppl_list, default=ppl_list[:5])
    filtered = [f for f in filtered if f["properties"]["PPL Baru"] in selected_ppl]
elif filter_level == "PML":
    pml_list = sorted(set(f["properties"]["PML Baru"] for f in filtered))
    selected_pml = st.sidebar.multiselect("Pilih PML:", pml_list, default=pml_list[:5])
    filtered = [f for f in filtered if f["properties"]["PML Baru"] in selected_pml]
elif filter_level == "PJ Kuda":
    pjk_list = sorted(set(f["properties"]["PJ KUDA"] for f in filtered))
    selected_pjk = st.sidebar.multiselect("Pilih PJ Kuda:", pjk_list, default=pjk_list)
    filtered = [f for f in filtered if f["properties"]["PJ KUDA"] in selected_pjk]

if not filtered:
    st.warning("Tidak ada data yang cocok dengan filter yang dipilih.")
    st.stop()

st.caption(f"Menampilkan {len(filtered)} subSLS teralokasi dari {len(set(f['properties']['nmkec'] for f in filtered))} kecamatan")

ppl_unique = sorted(set(f["properties"]["PPL Baru"] for f in filtered))
colormap_filtered = {k: v for k, v in colormap_ppl.items() if k in ppl_unique}

map_html = build_map(map_lat, map_lon, filtered, colormap_filtered, show_ppl_label)
st.components.v1.html(map_html, width=1400, height=750, scrolling=False)

st.markdown("---")
col1, col2, col3, col4 = st.columns(4)
col1.metric("SubSLS Teralokasi", len(filtered))
col2.metric("PPL", len(set(f["properties"]["PPL Baru"] for f in filtered)))
col3.metric("PML", len(set(f["properties"]["PML Baru"] for f in filtered)))
col4.metric("PJ Kuda", len(set(f["properties"]["PJ KUDA"] for f in filtered)))

st.subheader("Legenda Warna PPL")
legend_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-top:10px'>"
for ppl_name in ppl_unique:
    color = colormap_ppl[ppl_name]
    count = sum(1 for f in filtered if f["properties"]["PPL Baru"] == ppl_name)
    legend_html += f"<div style='display:flex;align-items:center;gap:5px;background:#f0f0f0;padding:4px 10px;border-radius:5px;border-left:4px solid {color}'><b style='color:{color}'>●</b> {ppl_name} ({count})</div>"
legend_html += "</div>"
st.markdown(legend_html, unsafe_allow_html=True)

st.subheader("Tabel Data Wilayah Tugas")
rows = []
for feat in filtered:
    p = feat["properties"]
    rows.append({
        "PPL": p.get("PPL Baru", "-"), "PML": p.get("PML Baru", "-"),
        "PJ Kuda": p.get("PJ KUDA", "-"), "Ketua SLS": p.get("nama_ketua", "-"),
        "Nama SLS": p.get("nmsls", "-"), "Desa": p.get("nmdesa", "-"),
        "Kecamatan": p.get("nmkec", "-"), "ID SubSLS": p.get("idsubsls", "-"),
        "Luas (ha)": round(p.get("luas", 0), 3),
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)
