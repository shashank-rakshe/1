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

A ribbon (Design/Sketch/Assembly/Detail/Inspect/Repair/Prepare/Sheet Metal
tabs, labeled button groups, a File menu) plus a Structure tree on the left
listing every solid — click a tree item to select it in the viewport. This
matches SpaceClaim's actual UI *paradigm* and terminology (Pull, Merge,
Combine, Sketch Mode, Inspect, Repair, Prepare); it is not a pixel copy of
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
- **Sketch Constraints** (with the Line tool) — Horizontal / Vertical /
  Distance / Parallel / Perpendicular / Equal Length. Place a few points,
  then apply a constraint by typing the point indices shown in the status
  bar (e.g. `0, 1` for Horizontal, `0, 1, 6.0` for Distance) — a small
  least-squares solver (`kernel/sketch_constraints.Sketch2D`) re-solves
  every non-fixed point so *all* constraints applied so far stay
  satisfied, not just the newest one. This is a real solver, not a demo:
  four wonky clicked points plus Horizontal/Vertical on each side and two
  Distance constraints will converge to an exact rectangle. Picking
  constrained points by typed index rather than by clicking them again in
  the viewport is a deliberate simplification — there's no existing
  mechanism to click an *already-placed* sketch point (only to place a
  new one).
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
  faces' default frames produce). Both are **live**: once applied, Moving
  or Rotating the part they're anchored to makes the constrained part
  automatically re-solve to stay coincident, like a real assembled
  component — not just a one-shot snap. **Anchor**: select one or more
  solids and toggle Anchor to lock their position — anchored parts show
  "(Anchored)" in the Structure tree and refuse Move/Rotate/Align/Orient
  (including being dragged along by someone else's live constraint)
  until un-anchored (also in the right-click menu).
- **Detail tab** — **Front / Top / Right / Isometric**: opens a 2D
  hidden-line-removed drawing view of the whole model in its own window
  (visible edges solid, hidden edges dashed), computed with OCCT's
  HLRBRep algorithm. This is SpaceClaim's Detail tab simplified to one
  view per window rather than multiple views laid out on a shared
  drawing sheet with a title block; there's no dimensioning yet either.
- **Sheet Metal tab** — **Flange**: toggle the tool, click an edge on a
  thin sheet to bend a new wall from it. The base face and the in-plane
  direction the flange extends are inferred from geometry (the largest
  planar face touching the edge, and the direction away from that
  face's centroid); a dialog then asks for thickness, wall length, bend
  angle, and bend radius. `kernel/sheet_metal.bend_allowance()` /
  `flat_length()` implement the standard K-factor bend-allowance formula
  (the flat-pattern length a bend adds) matching SpaceClaim's own Bend
  Allowances math. **Unfold**: same tool, same dialog, same edge pick —
  but instead of bending, it adds the flat extension a Flange with those
  exact parameters would need (design in flat state, fold later). This
  is the flat-pattern inverse of Flange specifically, reusing its own
  construction math; a general Unfold that flattens an arbitrary
  *already-bent* part (walking its whole face-adjacency graph to
  classify and unroll every bend) is a materially bigger, separate
  algorithm and isn't built.
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
plus a dialog-based alternative, a real sketch constraint solver
(Horizontal/Vertical/Distance/Parallel/Perpendicular/Equal Length),
sketch extrude and revolve, measure (distance/length/area/volume),
Repair (Stitch/Fill/Merge Faces), Prepare (Interference/Enclosure/Share
Topology), STEP/IGES import-export, native project save/load, a ribbon
UI with original icons and a Structure tree, orbit/pan/zoom viewport
with solid/face/edge picking, Ctrl/Shift+click multi-select, a
selection-aware right-click context menu, Delete, Assembly (live Align
faces/axes and Orient edges that re-solve when the part they're anchored
to moves, Anchor to lock a part in place), Detail (Front/Top/Right/
Isometric hidden-line-removed 2D drawing views), and
Sheet Metal (Flange, Unfold, and standalone bend-allowance/flat-length
math). 103 kernel tests + a full end-to-end GUI smoke test (including
real synthesized mouse clicks) cover all of it.

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

The interactive sketcher draws real geometry as you click, and now has a
real constraint solver (`kernel/sketch_constraints.py`, a small Gauss-
Newton least-squares solver) for Horizontal/Vertical/Distance/Parallel/
Perpendicular/Equal Length — the piece that separates "click to draw"
from a true parametric sketcher. What it doesn't have yet: Coincident/
Angle constraints wired into the UI (the solver supports them; only the
ribbon buttons for the other six were built), and dragging an
already-placed point live (constraints apply via a typed point-index
dialog instead, since there's no mechanism to click an existing sketch
point rather than place a new one).

SpaceClaim's actual ribbon has 13 tabs total (Design, Sketch, Assembly,
Measure, Facets, Detail, Repair, Prepare, Workbench, Mesh, Sheet Metal,
Tools, Display, Keyshot). This project now covers Design/Sketch/Assembly/
Measure/Repair/Prepare/Detail/Sheet Metal (Measure+Prepare shown as
"Inspect"+"Prepare" here) — 8 of 13. Assembly currently has Align, Orient,
and Anchor, and Align/Orient are now *live*: apply one, then Move/Rotate
the part it was anchored to, and the constrained part re-solves to stay
coincident (`MainWindow._propagate_constraints_from`, using a face/edge
re-located by index -- valid across rigid transforms, not across booleans
or direct-edit, which rebuild topology). Real SpaceClaim's Assembly also
has full assembly-constraint components (Rigid/Tangent/Gear conditions,
multi-configuration mates, constraint-aware Move handles that disable
the axes a constraint already fixes); those aren't built -- this is a
single always-on Align/Orient relationship per part pair, not a general
constraint system with its own UI for reviewing/deleting constraints.
Detail currently opens
one hidden-line view per window with no sheet layout, title block, or
dimensioning — real SpaceClaim places multiple views on a shared
drawing sheet and lets you add dimension/annotation callouts; that
sheet-layout layer isn't built. Sheet Metal currently has Flange and
Unfold (the latter is the flat-pattern inverse of Flange specifically,
not a general one) plus the bend-allowance/flat-length math. Not built
at all: sketch constraints beyond the six wired up (Coincident/Angle
exist in the solver but have no ribbon button), Fold/Flatten for
already-multi-bend parts, and a general Unfold that flattens an
arbitrary already-bent part by walking its face-adjacency graph. Out of
scope: Facets/Mesh/Workbench (ANSYS's simulation pipeline) and Keyshot
(a separate third-party renderer) — those aren't CAD modeling.

Not possible: importing native `.scdoc` files (undocumented proprietary
ANSYS format — no open reader exists); a Parasolid kernel (commercial,
license-only). Use STEP/IGES as the exchange format instead.

## Packaging as an executable (Windows)

Three files at the repo root turn this into a real "download one file,
double-click, installed" experience for a user with no Python setup at
all — `dcad.spec` (PyInstaller: bundles the app + every dependency into
one `dcad.exe`), `installer.iss` (Inno Setup: wraps that exe into an
actual installer wizard with Start Menu/Desktop shortcuts and an
uninstaller), and `build_installer.bat`, which runs every step below in
one double-click.

All of this **must be built on Windows** — OCCT and Qt are compiled
native binaries, so a Linux box can't cross-compile a `.exe` (that's also
why this Linux dev session can't just hand you a finished installer
directly, or run `build_installer.bat` itself; someone needs to run it on
an actual Windows machine — there's no Windows environment available to
this session to build it in). Steps:

**Fastest path**: clone the repo, check out this branch, then
double-click `build_installer.bat` (or run it from a command prompt) —
it creates the virtual environment, installs dependencies, builds
`dist\dcad.exe`, and (if [Inno Setup](https://jrsoftware.org/isdl.php) is
installed) also builds `installer_output\dcad-setup.exe`. Needs Python
3.11+ on PATH; the script tells you if it's missing.

**Manual/step-by-step**, if you'd rather see each step:

```
git clone <this repo> dcad
cd dcad
git checkout claude/new-session-unba9h
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python main.py          REM sanity check: confirm the app runs from source first
pyinstaller dcad.spec
```

That produces `dist\dcad.exe` — a single file with every dependency
(PySide6, all of OCCT via OCP, numpy) bundled in; nothing else needs to
ship alongside it. It's already double-clickable and runnable as-is.

For an actual installer (Start Menu entry, uninstaller, no "just a loose
.exe on your Desktop" feel), also install [Inno Setup](https://jrsoftware.org/isdl.php)
(free) and run:

```
iscc installer.iss
```

Output: `installer_output\dcad-setup.exe` — that's the one file to hand to
a user. Running it is the entire install experience: a wizard, a Start
Menu shortcut, an optional Desktop shortcut, and a proper entry in "Add or
Remove Programs."

Neither file has been build-tested (this session has no Windows machine to
run them on) — OCCT packaging with PyInstaller is known to be finicky, so
if `dcad.exe` fails to launch after step 1, the most likely fix is a
missing native DLL that `collect_dynamic_libs("OCP")` didn't catch:
- Run `pyinstaller dcad.spec` and watch the console output for `WARNING:
  lib not found` lines — add any missing ones under `binaries=` in the spec.
- If it builds but crashes on startup with an import error, add the missing
  module name to `hidden_imports` in the spec and rebuild.
- Antivirus/SmartScreen may flag a fresh, unsigned `.exe` (from either
  PyInstaller or Inno Setup) — that's expected for an unsigned build, not a
  sign anything's wrong.
- The single-file build unpacks to a temp folder on every launch, so
  startup is a few seconds slower than a folder-based build would be; if
  that matters more than having one file, `dcad.spec` has the folder-build
  alternative commented in at the bottom (swap it in, then update
  `installer.iss`'s `[Files]`/`[Icons]` sections to point at
  `dist\dcad\dcad.exe` and package the whole `dist\dcad\*` folder instead).
