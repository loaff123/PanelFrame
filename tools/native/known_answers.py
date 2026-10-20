"""Independent, configuration-derived native fixture expectations.

This module deliberately imports no PanelFrame code and performs no transform
discovery. Dimensions come from the licensed source's Edge.Cuts bounding box;
centres, grid steps, rotations and export origins come from generator settings.
"""

from fractions import Fraction as F


SOURCE_BOUNDS = tuple(map(F, ("100", "74", "66.75", "22")))

CONFIGURATIONS = {
    "default": {
        "source": "source.csv", "panel": "panel-default.csv",
        "rows": 2, "cols": 2, "hspace": "3", "vspace": "3",
        "rotation": 90, "alternation": "rows",
        "page_anchor": "mt", "page_position": ["148.5", "20"],
        "source_aux": ["0", "0"], "panel_aux": ["0", "0"],
        "source_origin": "absolute", "panel_origin": "absolute",
    },
    "mixed": {
        "source": "source-mixed.csv", "panel": "panel-mixed.csv",
        "rows": 2, "cols": 2, "hspace": "3", "vspace": "3",
        "rotation": 90, "alternation": "cols",
        "page_anchor": "mt", "page_position": ["148.5", "20"],
        "source_aux": ["120", "80"], "panel_aux": ["10", "20"],
        "source_origin": "drill-place", "panel_origin": "drill-place",
    },
    "varied": {
        "source": "source-varied.csv", "panel": "panel-varied.csv",
        "rows": 3, "cols": 2, "hspace": "7.5", "vspace": "4.25",
        "rotation": 180, "alternation": "cols",
        "page_anchor": "tl", "page_position": ["35", "45"],
        "source_aux": ["111.25", "77.5"], "panel_aux": ["-5.5", "12.25"],
        "source_origin": "drill-place", "panel_origin": "drill-place",
    },
}


def decimal(value):
    """Exact terminating-decimal formatting, without Decimal context rounding."""
    value = F(value)
    sign = "-" if value < 0 else ""
    n, d = abs(value.numerator), value.denominator
    whole, remainder = divmod(n, d)
    digits = []
    while remainder:
        digit, remainder = divmod(remainder * 10, d)
        digits.append(str(digit))
        if len(digits) > 30:
            raise ValueError("Fixture calculation did not terminate")
    return sign + str(whole) + (("." + "".join(digits)) if digits else "")


def rotate(x, y, angle):
    return {
        0: (x, y), 90: (-y, x), 180: (-x, -y), 270: (y, -x)
    }[angle % 360]


def grid_transforms(name):
    """Return grid-labelled transforms from settings, without reading any CSV."""
    c = CONFIGURATIONS[name]
    left, top, width, height = SOURCE_BOUNDS
    cx, cy = left + width / 2, top + height / 2
    if c["rotation"] % 180:
        width, height = height, width
    dx, dy = width + F(c["hspace"]), height + F(c["vspace"])
    page_x, page_y = map(F, c["page_position"])
    panel_width = c["cols"] * width + (c["cols"] - 1) * F(c["hspace"])
    if c["page_anchor"] == "mt":
        page_x -= panel_width / 2
    sx, sy = map(F, c["source_aux"])
    px, py = map(F, c["panel_aux"])
    result = []
    for row in range(c["rows"]):
        for col in range(c["cols"]):
            alternation = row if c["alternation"] == "rows" else col
            angle = (c["rotation"] + (alternation % 2) * 180) % 360
            # CSV Cartesian coordinates: x = board_x - aux_x,
            # y = aux_y - board_y. KiCad board Y increases downward.
            rcx, rcy = rotate(cx - sx, sy - cy, angle)
            tx = page_x + width / 2 + col * dx - px - rcx
            ty = py - (page_y + height / 2 + row * dy) - rcy
            result.append({"grid_row": row, "grid_col": col,
                           "rotation_deg": angle,
                           "tx_mm": decimal(tx), "ty_mm": decimal(ty)})
    return result


def expected_document():
    cases = {}
    for name, c in CONFIGURATIONS.items():
        transforms = grid_transforms(name)
        cases[name] = {
            "source": c["source"], "panel": c["panel"],
            "source_origin": c["source_origin"], "panel_origin": c["panel_origin"],
            "source_rows": 64, "panel_rows": 64 * len(transforms),
            "expected_instances": len(transforms),
            "transforms": sorted(transforms, key=lambda t: (
                t["rotation_deg"], F(t["tx_mm"]), F(t["ty_mm"]))),
        }
    damaged = next(t for t in grid_transforms("varied")
                   if t["grid_row"] == 0 and t["grid_col"] == 0)
    cases["varied-edited"] = {
        **cases["varied"], "panel": "panel-varied-edited.csv",
        "complete_handoff": False, "complete_instances": 5,
        "complete_transforms": [t for t in cases["varied"]["transforms"] if t != damaged],
        "edited_transform": damaged,
        "edit": {"reference": "C1", "grid_row": 0, "grid_col": 0,
                 "x_delta_mm": "0.000001", "y_delta_mm": "0",
                 "method": "Native pcbnew footprint move after panelization; one internal unit"},
        "missing_pose_rows": 1, "extra_pose_rows": 1,
    }
    return {
        "schema_version": 1,
        "oracle": "Configuration-derived exact grid arithmetic; no product discovery",
        "profile": "kicad-9-pos-csv-mm-cartesian",
        "bounds_kicad_mm": list(map(decimal, SOURCE_BOUNDS)),
        "cases": cases,
        "unqualified_controls": {
            "bottom_negated": {
                "source": "source-mixed-bottom-negated.csv",
                "panel": "panel-mixed-bottom-negated.csv",
                "reason": "Exported with --bottom-negate-x; outside the declared common Cartesian profile",
            }
        },
    }
