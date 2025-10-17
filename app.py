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
    "diagrams.xlsx",                    # repo root
    "./data/diagrams.xlsx",             # common alt
    "/mnt/data/diagrams.xlsx",          # fallback for uploaded assets
]
OUTPUT_DIR = Path("./output")
LAYER_NAME = "Squares"

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
    # Load only the first sheet and target columns; ignore extras if present.
    df = pd.read_excel(path, engine="openpyxl")
    # Keep only the first four columns by position to be strict, then rename by header.
    # But if headers already exist with exact names, prefer them.
    expected = ["Tower Type", "Leg Type", "Distance to Center", "Square Side"]

    # Best-effort selection: if expected headers exist, use them; else fallback to first 4 cols
    if all(col in df.columns for col in expected):
        df = df[expected].copy()
    else:
        df = df.iloc[:, :4].copy()
        df.columns = expected

    # Drop rows that are completely empty in these columns
    df = df.dropna(how="all", subset=expected)
    # Strip whitespace from string columns
    df["Tower Type"] = df["Tower Type"].astype(str).str.strip()
    df["Leg Type"] = df["Leg Type"].astype(str).str.strip()

    # Distance & side to numeric; assume meters -> convert to mm
    # (Coerce errors to NaN; we’ll validate later)
    df["Distance to Center"] = pd.to_numeric(df["Distance to Center"], errors="coerce")
    df["Square Side"] = pd.to_numeric(df["Square Side"], errors="coerce")
    return df

def mm(val_m: float) -> float:
    return float(val_m) * 1000.0

def square_corners(center_x: float, center_y: float, side_mm: float):
    """Return 4-point axis-aligned square (closed) as a list of (x, y)."""
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
    # Codespaces generally won't have a Desktop; still try HOME/Desktop for local runs.
    home = Path(os.path.expanduser("~"))
    desktop = home / "Desktop"
    return desktop if desktop.exists() else None

def destination_path(filename: str) -> Path:
    # If Desktop exists, use it; else use ./output
    d = desktop_path()
    if d is not None:
        return d / filename
    return ensure_output_dir() / filename

def draw_squares_dxf(selected_rows: dict, side_mm: float, out_path: Path):
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    if LAYER_NAME not in doc.layers:
        doc.layers.new(name=LAYER_NAME)

    # Draw each chosen leg
    for leg_label, row in selected_rows.items():
        if row is None:
            continue
        dist_m = row["Distance to Center"]
        if pd.isna(dist_m):
            raise ValueError(f"Distance to Center is NaN for leg {leg_label}.")
        dist = mm(dist_m)
        angle = LEG_ANGLE_DEG[leg_label]
        cx, cy = polar_to_cart(dist, angle)
        pts = square_corners(cx, cy, side_mm)
        msp.add_lwpolyline(pts, dxfattribs={"layer": LAYER_NAME, "closed": True})

    # Modelspace only; no texts/dims added.
    # Units: ezdxf is unitless; we’ve treated numbers as millimeters consistently.
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

# Validate numeric columns exist
if df["Distance to Center"].isna().all() or df["Square Side"].isna().all():
    st.error("Distance to Center and/or Square Side columns are not numeric or are empty.")
    st.stop()

# Tower selector
towers = sorted(df["Tower Type"].dropna().unique().tolist())
tower = st.selectbox("Τύπος Πύργου", towers, index=0 if towers else None, placeholder="Επιλογή Πύργου")

if not tower:
    st.stop()

tower_df = df[df["Tower Type"] == tower].copy()

# From the selected tower, determine unique leg options and the (constant) square side
leg_options = sorted(tower_df["Leg Type"].dropna().unique().tolist())

# side should be constant within tower; take the first non-null
side_m_series = tower_df["Square Side"].dropna()
if side_m_series.empty:
    st.error(f"No Square Side value found for tower '{tower}'.")
    st.stop()
side_mm_val = mm(side_m_series.iloc[0])

st.markdown("#### Επιλογή")
col_a, col_b = st.columns(2)
col_c, col_d = st.columns(2)

leg_a = col_a.selectbox("Σκέλος a", options=leg_options, key="leg_a", index=None, placeholder="Επιλογή σκέλους a")
leg_b = col_b.selectbox("Σκέλος b", options=leg_options, key="leg_b", index=None, placeholder="Επιλογή σκέλους b")
leg_c = col_c.selectbox("Σκέλος c", options=leg_options, key="leg_c", index=None, placeholder="Επιλογή σκέλους c")
leg_d = col_d.selectbox("Σκέλος d", options=leg_options, key="leg_d", index=None, placeholder="Επιλογή σκέλους d")

# Collect selected rows (if chosen)
def row_for_leg(leg_str: str | None):
    if not leg_str:
        return None
    # Take the first row for this (Tower, Leg)
    r = tower_df[tower_df["Leg Type"] == leg_str].head(1)
    return r.iloc[0] if not r.empty else None

sel_rows = {
    "a": row_for_leg(leg_a),
    "b": row_for_leg(leg_b),
    "c": row_for_leg(leg_c),
    "d": row_for_leg(leg_d),
}

# Validate at least one leg picked
if all(v is None for v in sel_rows.values()):
    st.info("Επιλογή τουλάχιστον ενός σκέλους για δημιουργία DXF.")
    st.stop()

# Filename suggestion
default_filename = f"{tower.replace(' ', '_')}_εκσκαφή.dxf"
filename = st.text_input("DXF file name", value=default_filename)

# Generate button
if st.button("Δημιουργία DXF"):
    try:
        if not filename.lower().endswith(".dxf"):
            filename += ".dxf"
        out_path = destination_path(filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        created = draw_squares_dxf(sel_rows, side_mm=side_mm_val, out_path=out_path)
        st.success(f"DXF created: {created}")

        # Also offer a direct download for Codespaces convenience
        with open(created, "rb") as f:
            st.download_button(
                label="Download DXF",
                data=f.read(),
                file_name=os.path.basename(created),
                mime="application/dxf",
            )

        # Quick summary
        picked = [k for k, v in sel_rows.items() if v is not None]
        st.caption(
            f"Placed squares for legs: {', '.join(picked)} at angles "
            f"{', '.join(f'{k}:{LEG_ANGLE_DEG[k]}°' for k in picked)} "
            f"with side {side_mm_val:.0f} mm."
        )

    except Exception as e:
        st.error(f"Failed to create DXF: {e}")
