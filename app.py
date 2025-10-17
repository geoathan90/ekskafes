import math
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import ezdxf

# ----------------------------
# Config
# ----------------------------
EXCEL_PATH_CANDIDATES = [
    "diagrams.xlsx",
    "./data/diagrams.xlsx",
    "/mnt/data/diagrams.xlsx",
]

OUTPUT_DIR = Path("./output")
LAYER_SQUARES = "Squares"
LAYER_ANN = "Annotations"

# Text/line styling (in mm)
TEXT_HEIGHT_MM = 150.0           # readable in most default zooms; tweak as you like
DIM_TEXT_HEIGHT_MM = 160.0
NOTE_TEXT_HEIGHT_MM = 150.0
DIM_OFFSET_MM = 250.0            # how far to offset dimension labels from their lines
LEG_NOTE_OFFSET_MM = 200.0       # how far to offset the Greek leg labels from square centers
DIM_LINE_LTYPE = "DASHED"        # uses DXF built-in linetype if present

# Angles in degrees for each leg label (mathematical CCW from +X)
LEG_ANGLE_DEG = {
    "a": 225.0,
    "b": 135.0,
    "c": 45.0,
    "d": 315.0,
}

# ----------------------------
# Helpers
# ----------------------------
def find_excel() -> Path | None:
    for p in EXCEL_PATH_CANDIDATES:
        pp = Path(p)
        if pp.exists():
            return pp
    return None

def load_table(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, engine="openpyxl")
    expected = ["Tower Type", "Leg Type", "Distance to Center", "Square Side"]
    if all(col in df.columns for col in expected):
        df = df[expected].copy()
    else:
        df = df.iloc[:, :4].copy()
        df.columns = expected

    df = df.dropna(how="all", subset=expected)
    df["Tower Type"] = df["Tower Type"].astype(str).str.strip()
    df["Leg Type"] = df["Leg Type"].astype(str).str.strip()
    df["Distance to Center"] = pd.to_numeric(df["Distance to Center"], errors="coerce")
    df["Square Side"] = pd.to_numeric(df["Square Side"], errors="coerce")
    return df

def mm(val_m: float) -> float:
    return float(val_m) * 1000.0

def square_corners(center_x: float, center_y: float, side_mm: float):
    half = side_mm / 2.0
    x0, y0 = center_x - half, center_y - half
    x1, y1 = center_x + half, center_y + half
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]

def polar_to_cart(dist_mm: float, angle_deg: float):
    ang = math.radians(angle_deg)
    return dist_mm * math.cos(ang), dist_mm * math.sin(ang)

def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR

def desktop_path() -> Path | None:
    home = Path(os.path.expanduser("~"))
    desktop = home / "Desktop"
    return desktop if desktop.exists() else None

def destination_path(filename: str) -> Path:
    d = desktop_path()
    if d is not None:
        return d / filename
    return ensure_output_dir() / filename

def ensure_layers(doc) -> None:
    if LAYER_SQUARES not in doc.layers:
        doc.layers.new(name=LAYER_SQUARES)
    if LAYER_ANN not in doc.layers:
        doc.layers.new(name=LAYER_ANN)
    # Ensure dashed linetype exists for dim lines; fallback if not
    if "DASHED" not in doc.linetypes:
        # no-op; AutoCAD will still show a default if DASHED not found
        pass

def unit_vec(vx: float, vy: float):
    n = math.hypot(vx, vy)
    return (vx / n, vy / n) if n > 0 else (0.0, 0.0)

def perp_vec(vx: float, vy: float):
    # Rotate 90° CCW
    return (-vy, vx)

def add_mtext(msp, text: str, insert: tuple[float, float], height: float, layer: str):
    m = msp.add_mtext(text, dxfattribs={"layer": layer, "char_height": height})
    # set the insertion point (works across ezdxf versions)
    m.set_location(insert)
    return m

def add_annotations(msp, centers: dict, leg_rows: dict, side_mm: float):
    """
    centers: dict like {"a": (cx, cy), ...} for chosen legs only
    leg_rows: dict like {"a": row_or_None, ...} used for leg type strings
    side_mm: common square side
    """
    # 1) Distance dimensions: line from origin to each center + offset text with the length in mm
    origin = (0.0, 0.0)
    placed_any = False
    for leg, c in centers.items():
        if c is None:
            continue
        cx, cy = c
        # construction line
        #msp.add_line(origin, (cx, cy), dxfattribs={"layer": LAYER_ANN, "linetype": DIM_LINE_LTYPE})
        msp.add_line(origin, (cx, cy), dxfattribs={"layer": LAYER_ANN})
        # distance
        dist = math.hypot(cx, cy)
        # place label near the midpoint, offset perpendicular to the line for readability
        mx, my = (cx * 0.5, cy * 0.5)
        ux, uy = unit_vec(cx, cy)
        px, py = perp_vec(ux, uy)
        tx, ty = (mx + px * DIM_OFFSET_MM, my + py * DIM_OFFSET_MM)
        # Greco-style subscript letter is not standard; we’ll do d_a etc.
        label = f"d_{leg} = {dist:.0f} mm"
        add_mtext(msp, label, (tx, ty), DIM_TEXT_HEIGHT_MM, LAYER_ANN)
        placed_any = True

    # 2) One common side note (near any placed square center)
    if placed_any:
        # pick the first available leg center
        leg0, c0 = next((k, v) for k, v in centers.items() if v is not None)
        cx0, cy0 = c0
        # Put the side note a bit above/left of the center
        note_pos = (cx0 - 0.6 * side_mm, cy0 + 0.6 * side_mm)
        add_mtext(msp, f"Square side = {side_mm:.0f} mm", note_pos, NOTE_TEXT_HEIGHT_MM, LAYER_ANN)

    # 3) Leg notes near each square, using Greek label + leg type string
    #    Example: "Σκέλος a: +4/ +0,7"
    for leg, c in centers.items():
        if c is None:
            continue
        row = leg_rows.get(leg)
        leg_type_str = row["Leg Type"] if row is not None else ""
        # offset the note away from the square center in a gentle diagonal to avoid overlap
        cx, cy = c
        ang = math.radians(LEG_ANGLE_DEG[leg])
        # place note perpendicular-ish to the radial to keep it readable
        off_dir = perp_vec(math.cos(ang), math.sin(ang))
        nx = cx + off_dir[0] * LEG_NOTE_OFFSET_MM
        ny = cy + off_dir[1] * LEG_NOTE_OFFSET_MM
        greek_note = f"Σκέλος {leg}: {leg_type_str}"
        add_mtext(msp, greek_note, (nx, ny), TEXT_HEIGHT_MM, LAYER_ANN)

def draw_squares_dxf(selected_rows: dict, side_mm: float, out_path: Path, add_dims_and_notes: bool):
    doc = ezdxf.new(setup=True)
    ensure_layers(doc)
    msp = doc.modelspace()

    centers = {}
    # Draw each chosen leg’s square
    for leg_label, row in selected_rows.items():
        if row is None:
            centers[leg_label] = None
            continue
        dist_m = row["Distance to Center"]
        if pd.isna(dist_m):
            raise ValueError(f"Distance to Center is NaN for leg {leg_label}.")
        dist = mm(dist_m)
        angle = LEG_ANGLE_DEG[leg_label]
        cx, cy = polar_to_cart(dist, angle)
        centers[leg_label] = (cx, cy)
        pts = square_corners(cx, cy, side_mm)
        msp.add_lwpolyline(pts, dxfattribs={"layer": LAYER_SQUARES, "closed": True})

    if add_dims_and_notes:
        add_annotations(msp, centers=centers, leg_rows=selected_rows, side_mm=side_mm)

    doc.saveas(out_path)
    return out_path

# ----------------------------
# UI
# ----------------------------
st.set_page_config(page_title="Διάγραμμα Εκσκαφών", layout="centered")
st.title("Διάγραμμα Εκσκαφών")

excel_path = find_excel()
if not excel_path:
    st.error(
        "Could not find `diagrams.xlsx`. "
        "Please put it at the repo root (or ./data/diagrams.xlsx) and reload."
    )
    st.stop()

df = load_table(excel_path)

if df["Distance to Center"].isna().all() or df["Square Side"].isna().all():
    st.error("Distance to Center and/or Square Side columns are not numeric or are empty.")
    st.stop()

towers = sorted(df["Tower Type"].dropna().unique().tolist())
tower = st.selectbox("Τύπος Πύργου", towers, index=0 if towers else None, placeholder="Επιλογή Πύργου")
if not tower:
    st.stop()

tower_df = df[df["Tower Type"] == tower].copy()
leg_options = sorted(tower_df["Leg Type"].dropna().unique().tolist())

side_m_series = tower_df["Square Side"].dropna()
if side_m_series.empty:
    st.error(f"No Square Side value found for tower '{tower}'.")
    st.stop()
side_mm_val = mm(side_m_series.iloc[0])

st.markdown("#### Επιλογή Σκελών")
col_a, col_b = st.columns(2)
col_c, col_d = st.columns(2)

leg_a = col_a.selectbox("Σκέλος a", options=leg_options, key="leg_a", index=None, placeholder=" a")
leg_b = col_b.selectbox("Σκέλος b", options=leg_options, key="leg_b", index=None, placeholder=" b")
leg_c = col_c.selectbox("Σκέλος c", options=leg_options, key="leg_c", index=None, placeholder=" c")
leg_d = col_d.selectbox("Σκέλος d", options=leg_options, key="leg_d", index=None, placeholder=" d")

def row_for_leg(leg_str: str | None):
    if not leg_str:
        return None
    r = tower_df[tower_df["Leg Type"] == leg_str].head(1)
    return r.iloc[0] if not r.empty else None

sel_rows = {
    "a": row_for_leg(leg_a),
    "b": row_for_leg(leg_b),
    "c": row_for_leg(leg_c),
    "d": row_for_leg(leg_d),
}

if all(v is None for v in sel_rows.values()):
    st.info("Επιλογή τουλάχιστον ενός σκέλους για δημιουργία DXF.")
    st.stop()

default_filename = f"{tower.replace(' ', '_')}.dxf"
filename = st.text_input("Όνομα αρχείου DXF", value=default_filename)

add_ann = st.checkbox("Εμφάνιση διαστάσεων", value=True)

if st.button("Δημιουργία DXF"):
    try:
        if not filename.lower().endswith(".dxf"):
            filename += ".dxf"
        out_path = destination_path(filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        created = draw_squares_dxf(
            sel_rows,
            side_mm=side_mm_val,
            out_path=out_path,
            add_dims_and_notes=add_ann,
        )
        st.success(f"DXF created: {created}")
        with open(created, "rb") as f:
            st.download_button(
                label="Download DXF",
                data=f.read(),
                file_name=os.path.basename(created),
                mime="application/dxf",
            )

        # picked = [k for k, v in sel_rows.items() if v is not None]
        # st.caption(
        #     f"Placed squares for legs: {', '.join(picked)} at angles "
        #     f"{', '.join(f'{k}:{LEG_ANGLE_DEG[k]}°' for k in picked)} "
        #     f"with side {side_mm_val:.0f} mm. "
        #     f"{'Annotations included.' if add_ann else 'No annotations.'}"
        # )

    except Exception as e:
        st.error(f"Failed to create DXF: {e}")
