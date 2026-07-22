"""Main application window: toolbar-driven direct-modeling CAD shell."""

from PySide6.QtWidgets import (
    QMainWindow,
    QToolBar,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QStatusBar,
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt

from dcad.kernel.document import Document
from dcad.kernel import primitives, booleans, direct_edit, io_step, transform, fillet, project_io, sketch
from dcad.viewport.viewport_widget import ViewportWidget
from dcad.viewport.occt_viewer import MODE_SOLID, MODE_FACE, MODE_EDGE
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE

# tool name -> (pick mode, status hint)
_TOOL_MODES = {
    "pull": (MODE_FACE, "Pull/Push: click a face"),
    "fillet": (MODE_EDGE, "Fillet: click an edge"),
    "chamfer": (MODE_EDGE, "Chamfer: click an edge"),
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("dcad — direct-modeling CAD")
        self.resize(1200, 800)

        self.document = Document()
        self.viewport = ViewportWidget(self)
        self.setCentralWidget(self.viewport)
        self.viewport.picked.connect(self._on_picked)

        self.active_tool = "select"
        self._tool_actions = {}

        self._build_toolbar()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")

    # -- toolbar -----------------------------------------------------
    def _build_toolbar(self):
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addAction(self._action("Box", self.add_box))
        tb.addAction(self._action("Cylinder", self.add_cylinder))
        tb.addAction(self._action("Sphere", self.add_sphere))
        tb.addSeparator()

        tb.addAction(self._action("Sketch Rect+Extrude", self.do_sketch_rect_extrude))
        tb.addAction(self._action("Sketch Circle+Extrude", self.do_sketch_circle_extrude))
        tb.addAction(self._action("Sketch Revolve", self.do_sketch_revolve))
        tb.addSeparator()
        tb.addAction(self._action("Union", self.do_union))
        tb.addAction(self._action("Subtract", self.do_subtract))
        tb.addAction(self._action("Intersect", self.do_intersect))
        tb.addSeparator()

        tb.addAction(self._tool_action("pull", "Pull/Push"))
        tb.addAction(self._tool_action("fillet", "Fillet"))
        tb.addAction(self._tool_action("chamfer", "Chamfer"))
        tb.addSeparator()

        tb.addAction(self._action("Move", self.do_move))
        tb.addAction(self._action("Rotate", self.do_rotate))
        tb.addAction(self._action("Copy", self.do_copy))
        tb.addSeparator()

        undo_action = self._action("Undo", self.undo)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        tb.addAction(undo_action)
        redo_action = self._action("Redo", self.redo)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        tb.addAction(redo_action)
        tb.addSeparator()

        tb.addAction(self._action("Open STEP...", self.open_step))
        tb.addAction(self._action("Save STEP...", self.save_step))
        tb.addAction(self._action("Open Project...", self.open_project))
        tb.addAction(self._action("Save Project...", self.save_project))
        tb.addSeparator()
        tb.addAction(self._action("Fit All", self.viewport.fit_all))

    def _action(self, label: str, slot) -> QAction:
        action = QAction(label, self)
        action.triggered.connect(slot)
        return action

    def _tool_action(self, tool_name: str, label: str) -> QAction:
        action = QAction(label, self)
        action.setCheckable(True)
        action.toggled.connect(lambda checked, name=tool_name: self._on_tool_toggled(name, checked))
        self._tool_actions[tool_name] = action
        return action

    def _on_tool_toggled(self, tool_name: str, checked: bool):
        if checked:
            for name, action in self._tool_actions.items():
                if name != tool_name and action.isChecked():
                    action.blockSignals(True)
                    action.setChecked(False)
                    action.blockSignals(False)
            self.active_tool = tool_name
            mode, hint = _TOOL_MODES[tool_name]
            self.viewport.clear_selection()
            self.viewport.viewer.set_pick_mode(mode)
            self.statusBar().showMessage(hint)
        elif self.active_tool == tool_name:
            self.active_tool = "select"
            self.viewport.clear_selection()
            self.viewport.viewer.set_pick_mode(MODE_SOLID)
            self.statusBar().showMessage("Ready")

    # -- primitives ----------------------------------------------------
    def add_box(self):
        self.document.snapshot()
        shape = primitives.make_box(2, 2, 2)
        self._add_to_scene(shape)

    def add_cylinder(self):
        self.document.snapshot()
        shape = primitives.make_cylinder(1, 2)
        self._add_to_scene(shape)

    def add_sphere(self):
        self.document.snapshot()
        shape = primitives.make_sphere(1)
        self._add_to_scene(shape)

    def _add_to_scene(self, shape, name: str = ""):
        obj = self.document.add(shape, name=name)
        self.viewport.viewer.display_shape(obj.id, shape)
        self.viewport.fit_all()
        self.statusBar().showMessage(f"Added {obj.name}")
        return obj

    # -- booleans --------------------------------------------------------
    def _selected_pair(self):
        ids = self.viewport.selected_shape_ids()
        if len(ids) != 2:
            QMessageBox.information(self, "Select two solids", "Select exactly two solids (click, then Shift+click a second) before running a boolean operation.")
            return None
        objs = [self.document.get(i) for i in ids]
        if any(o is None for o in objs):
            return None
        return objs

    def _selected_single(self):
        ids = self.viewport.selected_shape_ids()
        if len(ids) != 1:
            QMessageBox.information(self, "Select one solid", "Select exactly one solid first.")
            return None
        return self.document.get(ids[0])

    def _apply_boolean(self, op, label: str):
        pair = self._selected_pair()
        if pair is None:
            return
        a, b = pair
        try:
            result = op(a.shape, b.shape)
        except Exception as exc:
            QMessageBox.warning(self, f"{label} failed", str(exc))
            return
        self.document.snapshot()
        self.viewport.viewer.remove_shape(a.id)
        self.viewport.viewer.remove_shape(b.id)
        self.document.remove(a)
        self.document.remove(b)
        new_obj = self.document.add(result, name=f"{label}Result")
        self.viewport.viewer.display_shape(new_obj.id, result)
        self.viewport.update()
        self.statusBar().showMessage(f"{label} complete -> {new_obj.name}")

    def do_union(self):
        self._apply_boolean(booleans.union, "Union")

    def do_subtract(self):
        self._apply_boolean(booleans.subtract, "Subtract")

    def do_intersect(self):
        self._apply_boolean(booleans.intersect, "Intersect")

    # -- sketch (rectangle/circle profile) + extrude / revolve ------------
    def _prompt_floats(self, title: str, label: str, defaults: tuple):
        text, ok = QInputDialog.getText(
            self, title, label, text=", ".join(f"{v:g}" for v in defaults),
        )
        if not ok:
            return None
        try:
            values = tuple(float(v.strip()) for v in text.split(","))
        except ValueError:
            QMessageBox.warning(self, title, f"Enter {len(defaults)} comma-separated numbers")
            return None
        if len(values) != len(defaults):
            QMessageBox.warning(self, title, f"Enter exactly {len(defaults)} comma-separated numbers")
            return None
        return values

    def do_sketch_rect_extrude(self):
        corners = self._prompt_floats("Sketch Rectangle", "x0, y0, x1, y1:", (0.0, 0.0, 2.0, 2.0))
        if corners is None:
            return
        height, ok = QInputDialog.getDouble(self, "Extrude", "Height:", 2.0, -1000.0, 1000.0, 3)
        if not ok:
            return
        try:
            profile = sketch.rectangle_profile(*corners)
            solid = sketch.extrude(profile, height)
        except Exception as exc:
            QMessageBox.warning(self, "Sketch Rectangle+Extrude failed", str(exc))
            return
        self.document.snapshot()
        self._add_to_scene(solid, name="SketchExtrude")

    def do_sketch_circle_extrude(self):
        params = self._prompt_floats("Sketch Circle", "cx, cy, radius:", (0.0, 0.0, 1.0))
        if params is None:
            return
        height, ok = QInputDialog.getDouble(self, "Extrude", "Height:", 2.0, -1000.0, 1000.0, 3)
        if not ok:
            return
        try:
            profile = sketch.circle_profile(*params)
            solid = sketch.extrude(profile, height)
        except Exception as exc:
            QMessageBox.warning(self, "Sketch Circle+Extrude failed", str(exc))
            return
        self.document.snapshot()
        self._add_to_scene(solid, name="SketchExtrude")

    def do_sketch_revolve(self):
        params = self._prompt_floats(
            "Sketch Revolve Profile", "r0, z0, r1, z1 (radius/height rectangle in the XZ plane):",
            (1.0, 0.0, 2.0, 2.0),
        )
        if params is None:
            return
        angle, ok = QInputDialog.getDouble(self, "Revolve", "Angle (degrees, about Z axis):", 360.0, 0.001, 360.0, 2)
        if not ok:
            return
        try:
            profile = sketch.revolve_profile_rectangle(*params)
            solid = sketch.revolve(profile, angle)
        except Exception as exc:
            QMessageBox.warning(self, "Sketch Revolve failed", str(exc))
            return
        self.document.snapshot()
        self._add_to_scene(solid, name="SketchRevolve")

    # -- move / rotate / copy -------------------------------------------
    def _prompt_xyz(self, title: str, default=(0.0, 0.0, 0.0)):
        text, ok = QInputDialog.getText(
            self, title, "dx, dy, dz:", text=f"{default[0]:g}, {default[1]:g}, {default[2]:g}",
        )
        if not ok:
            return None
        try:
            dx, dy, dz = (float(v.strip()) for v in text.split(","))
        except ValueError:
            QMessageBox.warning(self, title, "Enter three comma-separated numbers, e.g. 5, 0, 0")
            return None
        return dx, dy, dz

    def do_move(self):
        obj = self._selected_single()
        if obj is None:
            return
        offset = self._prompt_xyz("Move")
        if offset is None:
            return
        self.document.snapshot()
        new_shape = transform.translate(obj.shape, *offset)
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self.viewport.update()
        self.statusBar().showMessage(f"Moved {obj.name}")

    def do_rotate(self):
        obj = self._selected_single()
        if obj is None:
            return
        angle, ok = QInputDialog.getDouble(self, "Rotate", "Angle (degrees, about Z axis through origin):", 90.0, -3600.0, 3600.0, 2)
        if not ok:
            return
        self.document.snapshot()
        new_shape = transform.rotate(obj.shape, angle)
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self.viewport.update()
        self.statusBar().showMessage(f"Rotated {obj.name} by {angle:g} deg")

    def do_copy(self):
        obj = self._selected_single()
        if obj is None:
            return
        offset = self._prompt_xyz("Copy (offset)", default=(2.0, 0.0, 0.0))
        if offset is None:
            return
        self.document.snapshot()
        dup = transform.duplicate(obj.shape)
        moved = transform.translate(dup, *offset)
        self._add_to_scene(moved, name=f"{obj.name}Copy")

    # -- undo / redo ------------------------------------------------------
    def _refresh_viewport_from_document(self):
        self.viewport.viewer.clear_all()
        for obj in self.document.objects:
            self.viewport.viewer.display_shape(obj.id, obj.shape)
        self.viewport.update()

    def undo(self):
        if self.document.undo():
            self._refresh_viewport_from_document()
            self.statusBar().showMessage("Undo")
        else:
            self.statusBar().showMessage("Nothing to undo")

    def redo(self):
        if self.document.redo():
            self._refresh_viewport_from_document()
            self.statusBar().showMessage("Redo")
        else:
            self.statusBar().showMessage("Nothing to redo")

    # -- direct-modeling pull/push, fillet, chamfer -----------------------
    def _on_picked(self, shape, owner_id: int):
        if self.active_tool not in _TOOL_MODES or shape is None or owner_id < 0:
            return
        obj = self.document.get(owner_id)
        if obj is None:
            return

        if self.active_tool == "pull":
            if shape.ShapeType() != TopAbs_FACE:
                return
            self._apply_pull(obj, shape)
        elif self.active_tool in ("fillet", "chamfer"):
            if shape.ShapeType() != TopAbs_EDGE:
                return
            self._apply_edge_op(obj, shape, self.active_tool)

    def _apply_pull(self, obj, face):
        distance, ok = QInputDialog.getDouble(
            self, "Pull/Push face", "Distance (positive = pull out, negative = push in):",
            1.0, -1000.0, 1000.0, 3,
        )
        if not ok or distance == 0:
            return
        try:
            new_shape = direct_edit.pull_face(obj.shape, face, distance)
        except Exception as exc:
            QMessageBox.warning(self, "Pull/Push failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self.viewport.update()
        self.statusBar().showMessage(f"Pulled {obj.name} by {distance:g}")

    def _apply_edge_op(self, obj, edge, tool: str):
        label = "Fillet radius" if tool == "fillet" else "Chamfer distance"
        value, ok = QInputDialog.getDouble(self, label, f"{label}:", 0.5, 0.001, 1000.0, 3)
        if not ok:
            return
        try:
            if tool == "fillet":
                new_shape = fillet.fillet_edge(obj.shape, edge, value)
            else:
                new_shape = fillet.chamfer_edge(obj.shape, edge, value)
        except Exception as exc:
            QMessageBox.warning(self, f"{tool.capitalize()} failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self.viewport.update()
        self.statusBar().showMessage(f"{tool.capitalize()}ed {obj.name} by {value:g}")

    # -- file I/O ------------------------------------------------------
    def open_step(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open STEP", "", "STEP files (*.step *.stp)")
        if not path:
            return
        try:
            shape = io_step.import_step(path)
        except Exception as exc:
            QMessageBox.warning(self, "Open failed", str(exc))
            return
        self.document.snapshot()
        self._add_to_scene(shape)

    def save_step(self):
        if not self.document.objects:
            QMessageBox.information(self, "Nothing to save", "The document is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save STEP", "", "STEP files (*.step *.stp)")
        if not path:
            return
        try:
            io_step.export_step([o.shape for o in self.document.objects], path)
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path}")

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "dcad projects (*.dcadproj)")
        if not path:
            return
        try:
            loaded = project_io.load_project(path)
        except Exception as exc:
            QMessageBox.warning(self, "Open failed", str(exc))
            return
        self.document.snapshot()
        for obj in loaded.objects:
            self.document.add(obj.shape, obj.name)
        self._refresh_viewport_from_document()
        self.viewport.fit_all()
        self.statusBar().showMessage(f"Opened {path}")

    def save_project(self):
        if not self.document.objects:
            QMessageBox.information(self, "Nothing to save", "The document is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "dcad projects (*.dcadproj)")
        if not path:
            return
        try:
            project_io.save_project(self.document, path)
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path}")
