#!/usr/bin/env python3
# Minimal DXF: one line + a text label at the origin

import ezdxf
from ezdxf.lldxf.const import units as DXF_UNITS

doc = ezdxf.new(dxfversion="R2010")
doc.header["$INSUNITS"] = DXF_UNITS.Millimeter  # optional: tells CAD the units
msp = doc.modelspace()

# A 100 mm horizontal line across the origin
msp.add_line((-50, 0), (50, 0), dxfattribs={"layer": "Test"})

# A tiny label at (0,0)
msp.add_text("Hello DXF", dxfattribs={"height": 5, "layer": "Test"}).set_pos((0, 0), align="MIDDLE_CENTER")

doc.saveas("hello.dxf")
print("Wrote hello.dxf")
