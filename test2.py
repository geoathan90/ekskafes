#!/usr/bin/env python3
# Draw a 1000x1000 axis-aligned square centered 9000 mm from the origin at 45°

import math
import ezdxf

# --- Parameters ---
distance_mm = 9000.0
angle_deg = 45.0
square_size = 1000.0

# --- Derived values ---
angle_rad = math.radians(angle_deg)
cx = distance_mm * math.cos(angle_rad)
cy = distance_mm * math.sin(angle_rad)
h = square_size / 2.0

# Square corners (axis-aligned), closed polyline
square_pts = [
    (cx - h, cy - h),
    (cx + h, cy - h),
    (cx + h, cy + h),
    (cx - h, cy + h),
    (cx - h, cy - h),
]

# --- DXF doc ---
doc = ezdxf.new(dxfversion="R2010")
msp = doc.modelspace()
doc.header["$INSUNITS"] = 4  # 4 = millimeters

# Visual aids (optional)
msp.add_line((0, 0), (cx, cy), dxfattribs={"layer": "Construct"})   # ray from origin
msp.add_point((0, 0), dxfattribs={"layer": "Construct"})
msp.add_point((cx, cy), dxfattribs={"layer": "Construct"})

# Square
msp.add_lwpolyline(square_pts, dxfattribs={"closed": True, "layer": "Square"})

# Labels (compatible: set insertion directly)
txt1 = msp.add_text("Center @ 45°, 9000 mm", dxfattribs={"height": 150, "layer": "Annot"})
txt1.dxf.insert = (cx, cy + h + 200)  # a bit above the square

txt2 = msp.add_text("1000 x 1000 square", dxfattribs={"height": 150, "layer": "Annot"})
txt2.dxf.insert = (cx, cy - h - 350)

# Save
out = "square_45deg_9000mm.dxf"
doc.saveas(out)
print(f"Wrote {out}")
print(f"Center: ({cx:.3f}, {cy:.3f}) mm")
