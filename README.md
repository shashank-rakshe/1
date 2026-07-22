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
- **Open STEP... / Save STEP...** — import/export `.step`/`.stp` files.
- Mouse: left-drag to orbit, middle/right-drag to pan, wheel to zoom.

## Tests

```
pip install pytest
PYTHONPATH=src pytest tests/test_kernel.py
```

`tests/smoke_gui.py` exercises the full app (primitives, booleans, pull/push,
STEP round-trip) end-to-end; on Linux without a display, run it under Xvfb:

```
xvfb-run -a python3 tests/smoke_gui.py
```

## Project layout

```
src/dcad/
  kernel/     # geometry: primitives, booleans, direct-edit, STEP/IGES I/O
  viewport/   # OCCT viewer embedded in a Qt widget (camera, picking)
  ui/         # MainWindow / toolbar
```

## Status

Working: primitive creation, boolean ops, planar-face pull/push, STEP/IGES
import-export, orbit/pan/zoom viewport with solid/face picking.

Not yet built (real SpaceClaim features, prioritized on request): sketch-based
extrude/revolve, fillets/chamfers, assemblies, sheet metal, drawings.

Not possible: importing native `.scdoc` files (undocumented proprietary
Siemens format — no open reader exists); a Parasolid kernel (commercial,
license-only). Use STEP/IGES as the exchange format instead.

## Packaging as an executable

Not yet set up. PyInstaller is the intended tool, but the build must run on
the target OS — a Windows `.exe` has to be built on Windows (this project's
native dependencies, OCCT and Qt, are OS-specific compiled binaries; a Linux
box cannot cross-compile them). Ask to have the PyInstaller spec added when
you're ready to build one.
