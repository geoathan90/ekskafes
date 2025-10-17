#!/usr/bin/env python3
# Minimal DXF: one line + a text label at the origin (max compatibility)

import ezdxf

doc = ezdxf.new(dxfversion="R2010")
msp = doc.modelspace()

# A 100-unit horizontal line across the origin
msp.add_line((-50, 0), (50, 0), dxfattribs={"layer": "Test"})

# A tiny label at (0,0) — no alignment helpers, just set the insertion point
txt = msp.add_text("Hello DXF", dxfattribs={"height": 1, "layer": "Test"})
txt.dxf.insert = (50,50)

# (Optional) tell CAD the units by header code (safe across versions)
# 1=inches, 2=feet, 4=mm, 5=cm, 6=m
doc.header["$INSUNITS"] = 4  # millimeters

doc.saveas("hello2.dxf")
print("Wrote hello.dxf")
