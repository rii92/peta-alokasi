import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from folium import DivIcon
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import json

st.set_page_config(page_title="Peta Wilayah Tugas Mitra - Sanggau", layout="wide")


@st.cache_data
def load_data():
    gdf = gpd.read_file("Final_SLS_202516105.geojson")
    xl = pd.read_excel("data-alokasi-petugas.xlsx")
    xl["idsubsls"] = xl["idsubsls"].astype(str).str.strip()
    gdf["idsubsls"] = gdf["idsubsls"].astype(str).str.strip()
    cols = ["idsubsls", "PPL Baru", "PML Baru", "PJ KUDA", "nama_ketua"]
    df = gdf.merge(xl[cols].drop_duplicates(subset="idsubsls"), on="idsubsls", how="inner")
    df["luas"] = pd.to_numeric(df["luas"], errors="coerce")
    df["centroid_lat"] = df.geometry.centroid.y
    df["centroid_lon"] = df.geometry.centroid.x
    centroid = df.geometry.to_crs(epsg=3857).unary_union.centroid
    clat, clon = gpd.GeoSeries([centroid], crs="EPSG:3857").to_crs(epsg=4326).iloc[0].coords[0][::-1]
    geojson_data = json.loads(df.to_json())
    return df, clat, clon, geojson_data


@st.cache_data
def build_ppl_color_map(ppl_list):
    cmap = [
        "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
        "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
        "#469990", "#dcbeff", "#9A6324", "#fffac8", "#800000",
        "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9",
        "#e6beff", "#1ce6ff", "#ff34ff", "#ff4a46", "#008941",
    ]
    return {name: cmap[i % len(cmap)] for i, name in enumerate(sorted(ppl_list))}


@st.cache_data
def build_map_html(map_lat, map_lon, geojson_str, ppl_json, colormap_json, show_label):
    geojson_data = json.loads(geojson_str)
    colormap = json.loads(ppl_json)
    ppl_unique = sorted(colormap.keys())

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

    for ppl_name in ppl_unique:
        filtered = [f for f in geojson_data["features"] if f["properties"]["PPL Baru"] == ppl_name]
        count = len(filtered)
        fg = folium.FeatureGroup(name=f"PPL: {ppl_name} ({count} subSLS)")
        if filtered:
            folium.GeoJson(
                {"type": "FeatureCollection", "features": filtered},
                style_function=style_fn,
                highlight_function=highlight_fn,
                tooltip=folium.GeoJsonTooltip(
                    fields=tooltip_fields, aliases=tooltip_aliases,
                    localize=True, sticky=True, style=tooltip_style,
                ),
            ).add_to(fg)
        fg.add_to(m)

    mc = MarkerCluster(name="Titik Pusat SubSLS").add_to(m)
    for feature in geojson_data["features"]:
        props = feature["properties"]
        ppl = props["PPL Baru"]
        clat = props["centroid_lat"]
        clon = props["centroid_lon"]
        color = colormap.get(ppl, "#999999")
        luas_val = round(props["luas"], 3) if props.get("luas") else "-"
        popup_html = f"""<div style='font-family:Arial;min-width:250px'>
            <b style='font-size:14px;color:{color}'>PPL: {ppl}</b><hr style='margin:4px 0'>
            <b>PML:</b> {props.get('PML Baru','-')}<br><b>PJ Kuda:</b> {props.get('PJ KUDA','-')}<br>
            <b>Ketua SLS:</b> {props.get('nama_ketua','-')}<br><b>SLS:</b> {props.get('nmsls','-')}<br>
            <b>Desa:</b> {props.get('nmdesa','-')}<br><b>Kec:</b> {props.get('nmkec','-')}<br>
            <b>ID:</b> {props.get('idsubsls','-')}<br><b>Luas:</b> {luas_val} ha</div>"""
        folium.CircleMarker(
            location=[clat, clon], radius=4,
            color=color, fill=True, fill_color=color, fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{props.get('nmsls','-')} - {ppl}",
        ).add_to(mc)

    if show_label:
        fg_label = folium.FeatureGroup(name="Label Nama PPL", show=True)
        ppl_centroids = {}
        for f in geojson_data["features"]:
            p = f["properties"]
            pname = p["PPL Baru"]
            if pname not in ppl_centroids:
                ppl_centroids[pname] = {"lats": [], "lons": [], "count": 0}
            ppl_centroids[pname]["lats"].append(p["centroid_lat"])
            ppl_centroids[pname]["lons"].append(p["centroid_lon"])
            ppl_centroids[pname]["count"] += 1
        label_agg = pd.DataFrame([
            {"PPL Baru": k, "lat": sum(v["lats"])/len(v["lats"]),
             "lon": sum(v["lons"])/len(v["lons"]), "count": v["count"]}
            for k, v in ppl_centroids.items()
        ])
        for _, row in label_agg.iterrows():
            color = colormap.get(row["PPL Baru"], "#999999")
            label_html = f"""<div style="
                background-color:{color};color:white;font-weight:bold;font-size:12px;
                padding:3px 8px;border-radius:4px;white-space:nowrap;
                border:2px solid white;box-shadow:1px 1px 3px rgba(0,0,0,0.5);
                font-family:Arial;text-align:center;line-height:1.2;
            ">{row['PPL Baru']}<br><span style="font-size:10px;font-weight:normal">({int(row['count'])} subSLS)</span></div>"""
            folium.Marker(
                location=[row["lat"], row["lon"]],
                icon=DivIcon(html=label_html, icon_size=(180, 30), icon_anchor=(90, 15)),
            ).add_to(fg_label)
        fg_label.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m.get_root().render()


df, map_lat, map_lon, geojson_data_raw = load_data()
colormap_ppl = build_ppl_color_map(df["PPL Baru"].unique())

st.title("Peta Wilayah Tugas PPL, PML & PJ Kuda - Kab. Sanggau")
st.caption(f"Menampilkan {len(df)} subSLS teralokasi dari {df['nmkec'].nunique()} kecamatan")

st.sidebar.header("Opsi Tampilan")
show_ppl_label = st.sidebar.toggle("Tampilkan Nama PPL di Peta", value=False)

st.sidebar.header("Filter")
filter_level = st.sidebar.radio("Filter berdasarkan:", ["Semua", "Kecamatan", "Desa", "PPL", "PML", "PJ Kuda"])

if filter_level == "Kecamatan":
    kec_list = sorted(df["nmkec"].dropna().unique())
    selected_kec = st.sidebar.multiselect("Pilih Kecamatan:", kec_list, default=kec_list[:3])
    df = df[df["nmkec"].isin(selected_kec)]
elif filter_level == "Desa":
    kec_list = sorted(df["nmkec"].dropna().unique())
    selected_kec = st.sidebar.selectbox("Pilih Kecamatan:", ["Semua"] + kec_list)
    if selected_kec != "Semua":
        df = df[df["nmkec"] == selected_kec]
    desa_list = sorted(df["nmdesa"].dropna().unique())
    selected_desa = st.sidebar.multiselect("Pilih Desa:", desa_list, default=desa_list[:5])
    df = df[df["nmdesa"].isin(selected_desa)]
elif filter_level == "PPL":
    ppl_list = sorted(df["PPL Baru"].dropna().unique())
    selected_ppl = st.sidebar.multiselect("Pilih PPL:", ppl_list, default=ppl_list[:5])
    df = df[df["PPL Baru"].isin(selected_ppl)]
elif filter_level == "PML":
    pml_list = sorted(df["PML Baru"].dropna().unique())
    selected_pml = st.sidebar.multiselect("Pilih PML:", pml_list, default=pml_list[:5])
    df = df[df["PML Baru"].isin(selected_pml)]
elif filter_level == "PJ Kuda":
    pjk_list = sorted(df["PJ KUDA"].dropna().unique())
    selected_pjk = st.sidebar.multiselect("Pilih PJ Kuda:", pjk_list, default=pjk_list)
    df = df[df["PJ KUDA"].isin(selected_pjk)]

if len(df) == 0:
    st.warning("Tidak ada data yang cocok dengan filter yang dipilih.")
    st.stop()

ppl_unique = sorted(df["PPL Baru"].unique())
colormap_filtered = {k: v for k, v in colormap_ppl.items() if k in ppl_unique}

geojson_filtered = json.loads(df.to_json())

map_html = build_map_html(
    map_lat, map_lon,
    json.dumps(geojson_filtered),
    json.dumps(colormap_filtered),
    show_ppl_label,
)

st.components.v1.html(map_html, width=1400, height=750, scrolling=False)

st.markdown("---")
col1, col2, col3, col4 = st.columns(4)
col1.metric("SubSLS Teralokasi", len(df))
col2.metric("PPL", df["PPL Baru"].nunique())
col3.metric("PML", df["PML Baru"].nunique())
col4.metric("PJ Kuda", df["PJ KUDA"].nunique())

st.subheader("Legenda Warna PPL")
legend_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-top:10px'>"
for ppl_name in ppl_unique:
    color = colormap_ppl[ppl_name]
    count = len(df[df["PPL Baru"] == ppl_name])
    legend_html += f"<div style='display:flex;align-items:center;gap:5px;background:#f0f0f0;padding:4px 10px;border-radius:5px;border-left:4px solid {color}'><b style='color:{color}'>●</b> {ppl_name} ({count})</div>"
legend_html += "</div>"
st.markdown(legend_html, unsafe_allow_html=True)

st.subheader("Tabel Data Wilayah Tugas")
st.dataframe(df[["PPL Baru", "PML Baru", "PJ KUDA", "nama_ketua", "nmsls", "nmdesa", "nmkec", "idsubsls", "luas"]].rename(columns={
    "PPL Baru": "PPL", "PML Baru": "PML", "PJ KUDA": "PJ Kuda",
    "nama_ketua": "Ketua SLS", "nmsls": "Nama SLS", "nmdesa": "Desa",
    "nmkec": "Kecamatan", "idsubsls": "ID SubSLS", "luas": "Luas (ha)"
}).style.format({"Luas (ha)": "{:.3f}"}), use_container_width=True, height=400)
