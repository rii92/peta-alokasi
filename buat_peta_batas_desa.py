import json
import os
import geopandas as gpd
import folium
from folium import DivIcon
from playwright.sync_api import sync_playwright

gdf = gpd.read_file("Final_SLS_202516105.geojson")

CMAP = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#469990", "#9A6324",
    "#800000", "#aaffc3", "#808000", "#ffd8b1", "#000075",
]

NORTH_ARROW = """
<div style="position:absolute;top:20px;left:20px;z-index:1000;background:rgba(255,255,255,0.9);
            border-radius:8px;padding:8px;box-shadow:0 2px 6px rgba(0,0,0,0.4);text-align:center;">
  <svg width="60" height="70" viewBox="0 0 60 70" xmlns="http://www.w3.org/2000/svg">
    <polygon points="30,5 45,40 30,33 15,40" fill="#d32f2f" stroke="#111" stroke-width="1.5"/>
    <polygon points="30,65 45,40 30,47 15,40" fill="#757575" stroke="#111" stroke-width="1.5"/>
    <line x1="30" y1="5" x2="30" y2="65" stroke="#111" stroke-width="1.5"/>
    <text x="30" y="0" text-anchor="middle" font-size="14" font-weight="bold" fill="#111" font-family="Arial">U</text>
  </svg>
</div>
"""

SCALE_JS = """
<script>
  L.control.scale({metric: true, imperial: false, position: 'bottomleft'}).addTo(map);
</script>
"""

TITLE_HTML = """
<div style="position:absolute;bottom:20px;right:20px;z-index:1000;background:rgba(255,255,255,0.92);
            border-radius:8px;padding:10px 16px;box-shadow:0 2px 6px rgba(0,0,0,0.4);
            font-family:Arial;text-align:right;line-height:1.4;">
  <b style="font-size:16px;">{title}</b><br>
  <span style="font-size:12px;color:#555;">Batas Desa - Google Earth</span>
</div>
"""


def make_map(kec_name):
    sub = gdf[gdf["nmkec"] == kec_name].copy()
    desa = sub.dissolve(by="nmdesa", aggfunc="first").reset_index()
    desa["kec"] = kec_name
    desa["color"] = [CMAP[i % len(CMAP)] for i in range(len(desa))]

    bounds = desa.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

    m = folium.Map(location=center, zoom_start=13, tiles=None)
    padding = 10 if kec_name == "SEKAYAM" else 30
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]], padding=(padding, padding))

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Earth", name="Google Earth (Satelit)", overlay=False,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Jalan (Esri)", overlay=True, opacity=0.7,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Labels (Esri)", overlay=True, opacity=0.7,
    ).add_to(m)

    for _, row in desa.iterrows():
        feature = {
            "type": "Feature",
            "properties": {"nmdesa": row["nmdesa"], "kec": row["kec"]},
            "geometry": row["geometry"].__geo_interface__,
        }
        folium.GeoJson(
            {"type": "FeatureCollection", "features": [feature]},
            style_function=lambda f, c=row["color"]: {
                "fillColor": c, "color": "#111111", "weight": 3, "fillOpacity": 0.30,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["nmdesa", "kec"], aliases=["Desa:", "Kecamatan:"], sticky=True,
                style="background-color:white;border:2px solid #333;font-size:14px;padding:6px;",
            ),
        ).add_to(m)

        c = row["geometry"].centroid
        label = f"""<div style="
            color:white;font-weight:bold;font-size:14px;white-space:nowrap;
            font-family:Arial;text-align:center;line-height:1.1;
            text-shadow:2px 2px 2px #000,-1px -1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000,1px 1px 0 #000;
        ">{row['nmdesa']}</div>"""
        folium.Marker(
            location=[c.y, c.x],
            icon=DivIcon(html=label, icon_size=(160, 22), icon_anchor=(80, 11)),
        ).add_to(m)

    m.get_root().html.add_child(folium.Element(SCALE_JS))
    m.get_root().html.add_child(folium.Element(NORTH_ARROW))
    m.get_root().html.add_child(folium.Element(TITLE_HTML.format(title=f"KECAMATAN {kec_name}")))
    return m


def render_png(m, out_path, w=1600, h=1200):
    html_path = "_map_temp.html"
    m.save(html_path)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": w, "height": h})
        page.goto("file:///" + os.path.abspath(html_path).replace("\\", "/"))
        page.wait_for_timeout(6000)
        page.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": w, "height": h})
        browser.close()
    os.remove(html_path)
    print(f"OK -> {out_path}")


for kec in ["ENTIKONG", "SEKAYAM"]:
    m = make_map(kec)
    render_png(m, f"peta_batas_desa_{kec.lower()}.png")
