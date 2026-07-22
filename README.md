# dcad

A direct-modeling CAD app in the spirit of SpaceClaim: create solids, boolean
them together, push/pull faces directly, and exchange STEP/IGES files.

Built on [OCCT](https://dev.opencascade.org/) (via the [OCP](https://github.com/CadQuery/OCP)
Python bindings) and PySide6 (Qt).

## Setup

```
python -m venv .venv
```

Windows: `.venv\Scripts\activate`   ·   Linux/macOS: `source .venv/bin/activate`

```
pip install -r requirements.txt
python main.py
```

## UI

A ribbon (Design/Sketch tabs, labeled button groups, a File menu) plus a
Structure tree on the left listing every solid — click a tree item to select
it in the viewport. This matches SpaceClaim's actual UI *paradigm* and
terminology (Pull, Merge, Combine, Sketch Mode); it is not a pixel copy of
SpaceClaim's artwork or branding, which are Siemens' proprietary assets.

## Using the app

- **Box / Cylinder / Sphere** — add a primitive solid to the scene.
- **Union / Subtract / Intersect** — click one solid, then Shift+click a
  second, then run the operation.
- **Pull/Push** — toggle the tool, click a planar face, enter a distance
  (positive pulls material out, negative pushes it in).
- **Fillet / Chamfer** — toggle the tool, click an edge, enter a radius/distance.
- **Move / Rotate / Copy** — select one solid, then run the tool and enter
  the offset/angle (Rotate is about the Z axis through the origin in v1).
- **Sketch (Extrude) / Sketch (Revolve)** — toggle one, pick Line/Rectangle/
  Circle, click points directly in the viewport (a live preview follows
  the mouse), then **Finish Sketch** to pull every profile drawn into a
  solid. Line: click each point, double-click to close the polygon.
  Extrude sketches on the XY plane; Revolve sketches on the XZ plane
  (about the Z axis) — mixing them up produces a zero-volume result, so
  the tool keeps them separate. **Cancel Sketch** discards without adding
  anything. There's also a dialog-based version of the same idea (Sketch
  Rect+Extrude / Sketch Circle+Extrude / Sketch Revolve) for typing exact
  coordinates instead of clicking.
- **Undo / Redo** — toolbar buttons or Ctrl+Z / Ctrl+Shift+Z.
- **Open/Save STEP...** — import/export `.step`/`.stp` files (works with
  any real CAD tool, including SpaceClaim's own STEP export).
- **Open/Save Project...** — this tool's own `.dcadproj` format (a zip of
  BREP geometry + a name manifest). Not SpaceClaim's `.scdoc` — see Status.
- Mouse: left-drag to orbit, middle/right-drag to pan, wheel to zoom.

## Tests

```
pip install pytest
PYTHONPATH=src pytest tests/test_kernel.py
```

`tests/smoke_gui.py` exercises the full app end-to-end (primitives, booleans,
pull/push, fillet/chamfer, move/rotate/copy, undo/redo, dialog- and click-
driven sketch+extrude/revolve — including real synthesized mouse events
through the actual viewport widget, not just direct method calls — plus
STEP and project round-trips); on Linux without a display, run it under Xvfb:

```
xvfb-run -a python3 tests/smoke_gui.py
```

## Project layout

```
src/dcad/
  kernel/     # geometry: primitives, booleans, direct-edit, fillet/chamfer,
              # transform, STEP/IGES I/O, native project I/O, document/undo
  viewport/   # OCCT viewer embedded in a Qt widget (camera, picking)
  ui/         # MainWindow / toolbar
```

## Status

Working: primitive creation, boolean ops, planar-face pull/push,
fillet/chamfer, move/rotate/copy, undo/redo, interactive click-to-sketch
drawing (Line/Rectangle/Circle) plus a dialog-based alternative, sketch
extrude and revolve, STEP/IGES import-export, native project save/load,
orbit/pan/zoom viewport with solid/face/edge picking. 40 kernel tests + a
full end-to-end GUI smoke test (including real synthesized mouse clicks)
cover all of it.

The interactive sketcher draws real geometry as you click, but there's no
constraint solver — no dimensional constraints (exact length/angle), no
geometric constraints (parallel, coincident, tangent), no dragging to
adjust an already-placed point. That's the natural next layer if wanted:
it's what separates "click to draw" from a true parametric sketcher.

Not yet built (real SpaceClaim features, in progress): sketch constraints,
assemblies, sheet metal, drawings, measurement tools.

Not possible: importing native `.scdoc` files (undocumented proprietary
Siemens format — no open reader exists); a Parasolid kernel (commercial,
license-only). Use STEP/IGES as the exchange format instead.

## Packaging as an executable

Not yet set up. PyInstaller is the intended tool, but the build must run on
the target OS — a Windows `.exe` has to be built on Windows (this project's
native dependencies, OCCT and Qt, are OS-specific compiled binaries; a Linux
box cannot cross-compile them). Ask to have the PyInstaller spec added when
you're ready to build one.
