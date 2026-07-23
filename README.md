# dcad

A direct-modeling CAD app in the spirit of SpaceClaim: create solids, boolean
them together, push/pull faces directly, and exchange STEP/IGES files.

Built on [OCCT](https://dev.opencascade.org/) (via the [OCP](https://github.com/CadQuery/OCP)
Python bindings) and PySide6 (Qt).

**Target use case**: professional work on large structural/assembly models,
not just small demo parts — so opening and navigating a big STEP file needs
to stay fast and responsive, the same bar set by [Mayo](https://github.com/fougue/mayo)
(also OCCT-based). See "Performance" under Status for what's implemented
toward that and what's still open.

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

A ribbon (Design/Sketch/Assembly/Detail/Inspect/Repair/Prepare tabs, labeled
button groups, a File menu) plus a Structure tree on the left listing every
solid — click a tree item to select it in the viewport. This matches
SpaceClaim's actual UI *paradigm* and terminology (Pull, Merge, Combine,
Sketch Mode, Inspect, Repair, Prepare); it is not a pixel copy of
SpaceClaim's artwork or branding, which are ANSYS's proprietary assets.

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
  Circle/Polygon/Ellipse/3-Point Circle/3-Point Arc, click points directly
  in the viewport (a live preview follows the mouse), then **Close Sketch**.
  This matches SpaceClaim's real
  behavior: closing a sketch turns each closed profile into a flat,
  zero-thickness **Surface** — drawing a circle gives you a flat disc, not
  a cylinder. Select the Surface and **Pull** it to thicken it into a solid,
  or **Revolve** it to spin it into one about the Z axis. Line: click each
  point, double-click to close the polygon. Extrude sketches on the XY
  plane; Revolve sketches on the XZ plane — mixing them up produces a
  zero-volume result, so the tool keeps them separate. **Cancel Sketch**
  discards without adding anything. There's also a one-step dialog version
  (Sketch Rect+Extrude / Sketch Circle+Extrude / Sketch Revolve) that
  skips the Surface stage and goes straight to a solid, for typing exact
  coordinates instead of clicking.
- **Measure** (Inspect tab) — click a face to see its area, click a second
  face to see the distance between them.
- **Repair tab** — **Stitch**: select 2+ disjoint faces/surfaces, sews them
  into one solid if watertight. **Fill**: toggle the tool, click a face to
  remove it and heal the surrounding geometry (undo a fillet/chamfer/
  protrusion). **Merge Faces**: select one solid, unifies faces on the same
  underlying surface and removes the redundant edges between them.
- **Prepare tab** — **Interference**: reports every pair of solids in the
  document whose volumes overlap. **Enclosure**: select solid(s), enter a
  margin, builds the surrounding void as a new solid (e.g. a CFD domain).
  **Share Topology**: select 2+ touching solids, matches their contact-
  face/edge topology while keeping them as separate solids (unlike
  Merge/Combine, which welds them into one).
- **Assembly tab** — **Align**: toggle the tool, click the face to move,
  then click the face to align it to. Two planar faces are brought flush
  and facing each other (like two mating surfaces in contact); two
  cylindrical faces are made concentric (a pin seating in a hole).
  **Orient**: toggle the tool, click the (straight) edge to rotate, then
  the edge it should point the same way as — SpaceClaim's real follow-up
  to Align, for fixing the rotation *about* an axis/plane Align already
  made coincident (Align alone leaves that rotation at whatever the
  faces' default frames produce). **Anchor**: select one or more solids
  and toggle Anchor to lock their position — anchored parts show
  "(Anchored)" in the Structure tree and refuse Move/Rotate/Align/Orient
  until un-anchored (also in the right-click menu).
- **Detail tab** — **Front / Top / Right / Isometric**: opens a 2D
  hidden-line-removed drawing view of the whole model in its own window
  (visible edges solid, hidden edges dashed), computed with OCCT's
  HLRBRep algorithm. This is SpaceClaim's Detail tab simplified to one
  view per window rather than multiple views laid out on a shared
  drawing sheet with a title block; there's no dimensioning yet either.
- **Undo / Redo** — toolbar buttons or Ctrl+Z / Ctrl+Shift+Z.
- **Open/Save STEP...** — import/export `.step`/`.stp` files (works with
  any real CAD tool, including SpaceClaim's own STEP export).
- **Open/Save Project...** — this tool's own `.dcadproj` format (a zip of
  BREP geometry + a name manifest). Not SpaceClaim's `.scdoc` — see Status.
- Mouse: left-drag to orbit, middle/right-drag to pan, wheel to zoom,
  left-click to select. **Ctrl+click** or **Shift+click** adds the clicked
  item to the current selection instead of replacing it (matches
  SpaceClaim, which treats both modifiers the same way). **Right-click** on
  a selection opens a context menu (SpaceClaim's "Select" menu) with
  actions scoped to what's selected — Move/Rotate/Copy/Merge Faces for one
  solid, Merge/Subtract/Intersect/Stitch/Share Topology for two, Stitch/
  Share Topology for more, plus Delete/Select All/Deselect All/Fit All.
  **Delete** also works from the keyboard-equivalent toolbar action.

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
drawing (Line/Rectangle/Circle/Polygon/Ellipse/3-Point Circle/3-Point Arc)
plus a dialog-based alternative, sketch extrude and revolve, measure
(distance/length/area/volume), Repair (Stitch/Fill/Merge Faces), Prepare
(Interference/Enclosure/Share Topology), STEP/IGES import-export, native
project save/load, a ribbon UI with original icons and a Structure tree,
orbit/pan/zoom viewport with solid/face/edge picking, Ctrl/Shift+click
multi-select, a selection-aware right-click context menu, Delete,
Assembly (Align faces/axes, Orient edges, Anchor to lock a part in
place), and Detail (Front/Top/Right/Isometric hidden-line-removed 2D
drawing views). 77 kernel tests + a full end-to-end GUI smoke test
(including real synthesized mouse clicks) cover all of it.

### Performance (large models)

Since the target use is real structural/assembly models rather than small
demo parts, a few concrete levers are in place so this scales like a
production tool (Mayo/SpaceClaim), not a toy:

- **STEP import is off the UI thread.** `open_step()` runs the file read
  and mesh precompute on a `QThread` (`ui/workers.py`), so opening a large
  file doesn't freeze the window — a progress dialog stays responsive
  while it loads.
- **STEP import preserves per-part structure.** `import_step_multi()`
  (`kernel/io_step.py`) returns each root shape separately instead of
  flattening the whole file into one compound, so a big assembly opens as
  independently selectable/hideable/deletable parts, the same way it would
  in SpaceClaim or Mayo — not as one inert blob.
- **Tessellation is explicit, relative, and parallel.** `tessellate()`
  (`viewport/occt_viewer.py`) meshes each shape with `BRepMesh_
  IncrementalMesh` up front using a deflection scaled to that shape's own
  bounding-box diagonal (consistent visual quality regardless of model
  scale) and `isInParallel=True` (uses all cores), instead of relying on
  OCCT's implicit serial meshing on first display.
- Bulk imports use a single `fit_all()`/structure-tree rebuild after all
  parts are added (`_add_many_to_scene`), not one per part — rebuilding
  the tree per part would be O(n²) for an assembly with many components.

Benchmarked: importing + tessellating a synthetic 500-part STEP assembly
takes ~2s total off the UI thread. Not yet done: instanced rendering for
repeated parts, level-of-detail for distant geometry, and incremental/
streaming import for files too large to hold fully in memory — the next
layer if a real-world file turns out to need it.

The interactive sketcher draws real geometry as you click, but there's no
constraint solver — no dimensional constraints (exact length/angle), no
geometric constraints (parallel, coincident, tangent), no dragging to
adjust an already-placed point. That's the natural next layer if wanted:
it's what separates "click to draw" from a true parametric sketcher.

SpaceClaim's actual ribbon has 13 tabs total (Design, Sketch, Assembly,
Measure, Facets, Detail, Repair, Prepare, Workbench, Mesh, Sheet Metal,
Tools, Display, Keyshot). This project now covers Design/Sketch/Assembly/
Measure/Repair/Prepare/Detail (Measure+Prepare shown as "Inspect"+"Prepare"
here). Assembly currently has Align, Orient, and Anchor — real
SpaceClaim's Assembly also has full assembly-constraint components
(Rigid/Tangent/Gear conditions, multi-configuration mates that persist
and re-solve as parts move); those aren't built, so Align/Orient here
are one-shot moves, not a live constraint. Detail currently opens one
hidden-line view per window with no sheet layout, title block, or
dimensioning — real SpaceClaim places multiple views on a shared
drawing sheet and lets you add dimension/annotation callouts; that
sheet-layout layer isn't built. Not yet built at all: Sheet Metal,
sketch constraints. Out of scope: Facets/Mesh/Workbench (ANSYS's
simulation pipeline) and Keyshot (a separate third-party renderer) —
those aren't CAD modeling.

Not possible: importing native `.scdoc` files (undocumented proprietary
ANSYS format — no open reader exists); a Parasolid kernel (commercial,
license-only). Use STEP/IGES as the exchange format instead.

## Packaging as an executable

Not yet set up. PyInstaller is the intended tool, but the build must run on
the target OS — a Windows `.exe` has to be built on Windows (this project's
native dependencies, OCCT and Qt, are OS-specific compiled binaries; a Linux
box cannot cross-compile them). Ask to have the PyInstaller spec added when
you're ready to build one.
