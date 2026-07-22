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

## Using the app

- **Box / Cylinder / Sphere** — add a primitive solid to the scene.
- **Union / Subtract / Intersect** — click one solid, then Shift+click a
  second, then run the operation.
- **Pull/Push** — toggle the tool, click a planar face, enter a distance
  (positive pulls material out, negative pushes it in).
- **Fillet / Chamfer** — toggle the tool, click an edge, enter a radius/distance.
- **Move / Rotate / Copy** — select one solid, then run the tool and enter
  the offset/angle (Rotate is about the Z axis through the origin in v1).
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

`tests/smoke_gui.py` exercises the full app (primitives, booleans, pull/push,
fillet/chamfer, move/rotate/copy, undo/redo, STEP and project round-trips)
end-to-end; on Linux without a display, run it under Xvfb:

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
fillet/chamfer, move/rotate/copy, undo/redo, STEP/IGES import-export,
native project save/load, orbit/pan/zoom viewport with solid/face/edge
picking.

Not yet built (real SpaceClaim features, in progress): sketch-based
extrude/revolve, assemblies, sheet metal, drawings, measurement tools.

Not possible: importing native `.scdoc` files (undocumented proprietary
Siemens format — no open reader exists); a Parasolid kernel (commercial,
license-only). Use STEP/IGES as the exchange format instead.

## Packaging as an executable

Not yet set up. PyInstaller is the intended tool, but the build must run on
the target OS — a Windows `.exe` has to be built on Windows (this project's
native dependencies, OCCT and Qt, are OS-specific compiled binaries; a Linux
box cannot cross-compile them). Ask to have the PyInstaller spec added when
you're ready to build one.
