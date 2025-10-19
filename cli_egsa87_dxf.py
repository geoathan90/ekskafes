#!/usr/bin/env python3
import argparse
import math
from pathlib import Path

import ezdxf
import pandas as pd

# Same leg mapping as your app
LEG_ANGLE_DEG = {"a": 225.0, "b": 135.0, "c": 45.0, "d": 315.0}

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

def polar_xy(dist_m: float, angle_deg: float) -> tuple[float, float]:
    ang = math.radians(angle_deg)
    return dist_m * math.cos(ang), dist_m * math.sin(ang)

def square_corners_local(cx: float, cy: float, side_m: float):
    h = side_m / 2.0
    return [
        (cx - h, cy - h),
        (cx + h, cy - h),
        (cx + h, cy + h),
        (cx - h, cy + h),
        (cx - h, cy - h),  # close
    ]

def rot_ccw_about_origin(x: float, y: float, theta_deg_from_x: float) -> tuple[float, float]:
    t = math.radians(theta_deg_from_x)
    ct, st = math.cos(t), math.sin(t)
    return (x * ct - y * st, x * st + y * ct)

def main():
    p = argparse.ArgumentParser(description="Create geo-referenced DXF (EGSA-87) from diagrams.xlsx")
    p.add_argument("--excel", default="diagrams.xlsx", help="Path to diagrams.xlsx")
    p.add_argument("--tower", required=True, help="Tower Type (exact text as in Excel)")
    p.add_argument("--legs", nargs="+", choices=list(LEG_ANGLE_DEG.keys()),
                   required=True, help="Legs to include, e.g. a b c")
    p.add_argument("--easting", type=float, help="EGSA-87 Easting of site center (meters)")
    p.add_argument("--northing", type=float, help="EGSA-87 Northing of site center (meters)")
    p.add_argument("--azimuth", type=float, default=0.0,
                   help="Rotation CLOCKWISE from North (degrees). 0 means +Y aligns with North.")
    p.add_argument("--out", default="excavations_egsa87.dxf", help="Output DXF filename")
    args = p.parse_args()

    # If coords not passed, prompt interactively (keeps CLI flexible)
    if args.easting is None:
        args.easting = float(input("Center Easting (EGSA-87, m): ").strip())
    if args.northing is None:
        args.northing = float(input("Center Northing (EGSA-87, m): ").strip())
    if args.azimuth is None:
        args.azimuth = float(input("Azimuth clockwise from North (deg): ").strip())

    E0, N0 = args.easting, args.northing
    # Convert "clockwise from North" to math CCW-from-+X
    theta_from_x = 90.0 - float(args.azimuth)

    df = load_table(Path(args.excel))
    tdf = df[df["Tower Type"] == args.tower].copy()
    if tdf.empty:
        raise SystemExit(f"No rows found for Tower Type '{args.tower}' in {args.excel}")

    # Take square side from first non-null row (as your app does)
    side_series = tdf["Square Side"].dropna()
    if side_series.empty:
        raise SystemExit(f"No 'Square Side' value found for tower '{args.tower}'.")
    side_m = float(side_series.iloc[0])

    # Prepare DXF
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    doc.header["$INSUNITS"] = 6  # meters
    doc.header["$INSBASE"] = (E0, N0, 0.0)

    # Store lightweight CRS metadata using XDATA (readable in many tools)
    doc.appids.add("GEODATA")
    msp.set_xdata("GEODATA", [
        (1000, "CRS=EPSG:2100 (HGRS87 / Greek Grid)"),
        (1000, f"Origin_E={E0}"),
        (1000, f"Origin_N={N0}"),
        (1000, f"Azimuth_clockwise_from_North_deg={args.azimuth}"),
    ])

    # Draw each chosen leg's square
    for leg in args.legs:
        # First row per Leg Type (same approach as app)
        row = tdf[tdf["Leg Type"] == leg].head(1)
        if row.empty:
            print(f"Warning: no row for leg '{leg}' in tower '{args.tower}'. Skipping.")
            continue
        dist_m = float(row["Distance to Center"].iloc[0])
        angle_deg = LEG_ANGLE_DEG[leg]  # local-polar angle
        cx_local, cy_local = polar_xy(dist_m, angle_deg)
        # Axis-aligned square in local coords
        pts_local = square_corners_local(cx_local, cy_local, side_m)
        # Rotate about origin, then translate to EGSA-87 center
        pts_geo = []
        for (x, y) in pts_local:
            xr, yr = rot_ccw_about_origin(x, y, theta_from_x)
            pts_geo.append((E0 + xr, N0 + yr))
        msp.add_lwpolyline(pts_geo, dxfattribs={"closed": True, "layer": f"Square_{leg}"})

    # North arrow (5 m) at site center
    arrow_len = 5.0
    msp.add_line((E0, N0), (E0, N0 + arrow_len), dxfattribs={"layer": "North"})
    msp.add_text("N", dxfattribs={"height": 1.0, "layer": "North"}).set_pos((E0, N0 + arrow_len + 0.5))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out)
    print(f"Wrote {out.resolve()}")
    print(f"CRS: EPSG:2100 (EGSA-87). Origin: E={E0}, N={N0}. Azimuth cw from North: {args.azimuth}°")

if __name__ == "__main__":
    main()
