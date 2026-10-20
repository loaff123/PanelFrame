#!/usr/bin/python3
"""Regenerate native acceptance data using KiCad 9.0.2 and KiKit 1.8.1.

Use the Python interpreter that supplies pcbnew (normally /usr/bin/python3).
KIKIT may name an isolated KiKit executable. The output directory must be new.
No PanelFrame imports, network access, installation or manufacturing actions.
"""

import argparse
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from known_answers import CONFIGURATIONS, SOURCE_BOUNDS, expected_document, grid_transforms, rotate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    boards = root / "boards"
    boards.mkdir()
    for setting, subdir in (("XDG_CONFIG_HOME", "config"),
                            ("XDG_CACHE_HOME", "cache"), ("XDG_DATA_HOME", "data")):
        os.environ[setting] = str(root / subdir)
        (root / subdir).mkdir()
    # Delay pcbnew import until its writable XDG locations have been set.
    import pcbnew

    if pcbnew.Version() != "9.0.2":
        raise SystemExit("This recorded native acceptance gate requires KiCad 9.0.2")
    kikit = os.environ.get("KIKIT", "kikit")
    version = subprocess.check_output([kikit, "--version"], text=True).strip()
    if version != "kikit, version 1.8.1":
        raise SystemExit("This recorded native acceptance gate requires KiKit 1.8.1")
    cli_version = subprocess.check_output(["kicad-cli", "version"], text=True).strip()
    if cli_version != "9.0.2":
        raise SystemExit("Unexpected kicad-cli version: " + cli_version)
    commands = []

    def run(command):
        commands.append(command)
        with (root / "native-replay.log").open("a", encoding="utf-8") as log:
            log.write("COMMAND " + json.dumps(command) + "\n")
            log.flush()
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)

    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures/native"
    source_path = boards / "USB-C-FUSB302-PI.kicad_pcb"
    shutil.copyfile(fixture / "boards/USB-C-FUSB302-PI.kicad_pcb", source_path)
    shutil.copyfile(fixture / "LICENSE.board", root / "LICENSE.board")
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == (
        "2f3b4a62d4034342854fe1ac1c47c62f289756875668acf0320e72ff7868241d")
    assert hashlib.sha256((root / "LICENSE.board").read_bytes()).hexdigest() == (
        "e3bd2123ddfedf44c2b4078b86e3d6c5be483f3675612bfc6076bbacc03077c8")
    original = pcbnew.LoadBoard(str(source_path))
    # Source outline is rectangular and has these exact Edge.Cuts endpoints.
    # Assert via the native API; known-answer arithmetic remains constant input.
    # KiCad's BoardEdgesBoundingBox includes stroke width; inspect the centreline
    # endpoints instead to match KiKit's source bounding box.
    edges = [e for e in original.GetDrawings() if e.GetLayer() == pcbnew.Edge_Cuts]
    xs = [point.x for e in edges for point in (e.GetStart(), e.GetEnd())]
    ys = [point.y for e in edges for point in (e.GetStart(), e.GetEnd())]
    endpoint_bounds = tuple(F(v, 1000000) for v in (
        min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    assert endpoint_bounds == SOURCE_BOUNDS, (endpoint_bounds, SOURCE_BOUNDS)

    def origin(board, pair):
        board.GetDesignSettings().SetAuxOrigin(pcbnew.VECTOR2I(
            *[int(F(v) * 1000000) for v in pair]))

    def export(board, output, drill=False, negate=False):
        command = ["kicad-cli", "pcb", "export", "pos", "--format", "csv",
                   "--units", "mm", "--side", "both"]
        if drill:
            command.append("--use-drill-file-origin")
        if negate:
            command.append("--bottom-negate-x")
        run(command + ["-o", output, str(board)])

    native_sources, native_panels = {}, {}
    for name, c in CONFIGURATIONS.items():
        source_board = source_path
        if name != "default":
            board = pcbnew.LoadBoard(str(source_path))
            if name == "mixed":
                for footprint in board.GetFootprints():
                    if footprint.GetReference() in {"C1", "R1", "U1"}:
                        footprint.Flip(footprint.GetPosition(), False)
                    if footprint.GetReference() == "U2":
                        footprint.SetOrientation(pcbnew.EDA_ANGLE(17.125, pcbnew.DEGREES_T))
            origin(board, c["source_aux"])
            source_board = boards / ("source-" + name + ".kicad_pcb")
            pcbnew.SaveBoard(str(source_board), board)
        native_sources[name] = source_board
        export(source_board, c["source"], c["source_origin"] == "drill-place")
        panel_board = boards / ("panel-" + name + ".kicad_pcb")
        layout = (f"grid; rows: {c['rows']}; cols: {c['cols']}; "
                  f"hspace: {c['hspace']}mm; vspace: {c['vspace']}mm; "
                  f"rotation: {c['rotation']}deg; alternation: {c['alternation']}")
        command = [kikit, "panelize", "--layout", layout, "--tabs", "full",
                   "--cuts", "vcuts", "--post", "refill: false",
                   "--dump", "preset-" + name + ".json"]
        if name == "varied":
            command += ["--page", "anchor: tl; posx: 35mm; posy: 45mm"]
        run(command + [str(source_board), str(panel_board)])
        if c["panel_origin"] == "drill-place":
            panel = pcbnew.LoadBoard(str(panel_board))
            origin(panel, c["panel_aux"])
            pcbnew.SaveBoard(str(panel_board), panel)
        native_panels[name] = panel_board
        export(panel_board, c["panel"], c["panel_origin"] == "drill-place")

    # A true post-panel native edit, chosen with configuration-derived coordinates.
    c = CONFIGURATIONS["varied"]
    source = pcbnew.LoadBoard(str(native_sources["varied"]))
    original_c1 = [f for f in source.GetFootprints() if f.GetReference() == "C1"]
    assert len(original_c1) == 1
    source_position = original_c1[0].GetPosition()
    sx, sy = map(F, c["source_aux"])
    x, y = F(source_position.x, 1000000) - sx, sy - F(source_position.y, 1000000)
    t = next(t for t in grid_transforms("varied") if t["grid_row"] == t["grid_col"] == 0)
    x, y = rotate(x, y, t["rotation_deg"])
    x, y = x + F(t["tx_mm"]), y + F(t["ty_mm"])
    px, py = map(F, c["panel_aux"])
    target = (int((x + px) * 1000000), int((py - y) * 1000000))
    panel = pcbnew.LoadBoard(str(native_panels["varied"]))
    selected = [f for f in panel.GetFootprints()
                if f.GetReference() == "C1" and (f.GetPosition().x, f.GetPosition().y) == target]
    assert len(selected) == 1, (target, len(selected))
    selected[0].Move(pcbnew.VECTOR2I(1, 0))
    edited = boards / "panel-varied-edited.kicad_pcb"
    pcbnew.SaveBoard(str(edited), panel)
    export(edited, "panel-varied-edited.csv", True)
    export(native_sources["mixed"], "source-mixed-bottom-negated.csv", True, True)
    export(native_panels["mixed"], "panel-mixed-bottom-negated.csv", True, True)

    (root / "expected.json").write_text(json.dumps(expected_document(), indent=2) + "\n")
    (root / "generation.json").write_text(json.dumps({
        "kicad": cli_version, "pcbnew": pcbnew.Version(), "kikit": "1.8.1",
        "commands": commands, "configuration": CONFIGURATIONS,
        "native_outline_endpoint_bounds_mm": [str(v) for v in endpoint_bounds],
        "negative_edit": {"reference": "C1", "before_kicad_internal_units": list(target),
                          "after_kicad_internal_units": [target[0] + 1, target[1]],
                          "internal_units_per_mm": 1000000},
        "generated_files_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and
            p.suffix in {".csv", ".kicad_pcb", ".json"}
        },
    }, indent=2) + "\n")
    from check_fixtures import check
    result = check(root)
    (root / "known-answer-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
