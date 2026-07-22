"""Main application window: toolbar-driven direct-modeling CAD shell."""

from PySide6.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QStatusBar,
    QMenu,
    QDockWidget,
    QTreeWidget,
    QTreeWidgetItem,
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt

from dcad.kernel.document import Document
from dcad.kernel import primitives, booleans, direct_edit, io_step, transform, fillet, project_io, sketch, measure
from dcad.viewport.viewport_widget import ViewportWidget
from dcad.viewport.occt_viewer import MODE_SOLID, MODE_FACE, MODE_EDGE
from dcad.ui.ribbon import RibbonBar
from dcad.ui.theme import STYLESHEET
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.gp import gp_Ax3, gp_Pnt, gp_Dir

# Sketch entities are given temporary negative ids so they never collide
# with document objects (positive ids from an itertools.count(1)) or the
# viewport's PREVIEW_ID (-1).
_SKETCH_TEMP_ID_BASE = -100

# tool name -> (pick mode, status hint)
_TOOL_MODES = {
    "pull": (MODE_FACE, "Pull/Push: click a face"),
    "fillet": (MODE_EDGE, "Fillet: click an edge"),
    "chamfer": (MODE_EDGE, "Chamfer: click an edge"),
    "measure": (MODE_FACE, "Measure: click a face for its area, or click a second face for the distance between them"),
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
        self.viewport.sketch_clicked.connect(self._on_sketch_clicked)
        self.viewport.sketch_hover.connect(self._on_sketch_hover)
        self.viewport.sketch_double_clicked.connect(self._on_sketch_finish_entity)

        self.active_tool = "select"
        self._tool_actions = {}
        self.measure_picks = []

        self.interactive_sketch_active = False
        self.interactive_sketch_finish_mode = None  # "extrude" | "revolve"
        self.interactive_sketch_tool = None  # "line" | "rect" | "circle"
        self.interactive_sketch_points = []
        self.interactive_sketch_profiles = []
        self._interactive_sketch_shape_ids = []
        self.sketch_entity_actions = {}

        self.setStyleSheet(STYLESHEET)
        self._build_ribbon()
        self._build_structure_tree()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")

    # -- ribbon -----------------------------------------------------
    def _build_ribbon(self):
        self.ribbon = RibbonBar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._wrap_in_toolbar(self.ribbon))

        file_menu = QMenu(self.ribbon.file_button)
        file_menu.addAction(self._action("Open STEP...", self.open_step))
        file_menu.addAction(self._action("Save STEP...", self.save_step))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Open Project...", self.open_project))
        file_menu.addAction(self._action("Save Project...", self.save_project))
        self.ribbon.file_button.setMenu(file_menu)

        design_tab = self.ribbon.add_tab("Design")

        select_group = design_tab.add_group("Select")
        select_group.add_action(self._action("Select", self.select_tool))

        create_group = design_tab.add_group("Create")
        create_group.add_action(self._action("Box", self.add_box))
        create_group.add_action(self._action("Cylinder", self.add_cylinder))
        create_group.add_action(self._action("Sphere", self.add_sphere))

        edit_group = design_tab.add_group("Edit")
        edit_group.add_action(self._tool_action("pull", "Pull"))
        edit_group.add_action(self._action("Move", self.do_move))
        edit_group.add_action(self._action("Rotate", self.do_rotate))
        edit_group.add_action(self._action("Copy", self.do_copy))

        combine_group = design_tab.add_group("Combine")
        combine_group.add_action(self._action("Merge", self.do_union))
        combine_group.add_action(self._action("Subtract", self.do_subtract))
        combine_group.add_action(self._action("Intersect", self.do_intersect))

        construct_group = design_tab.add_group("Construct")
        construct_group.add_action(self._tool_action("fillet", "Fillet"))
        construct_group.add_action(self._tool_action("chamfer", "Chamfer"))

        sketch_mode_group = design_tab.add_group("Sketch Mode")
        self.sketch_extrude_action = QAction("Extrude\nPlane", self)
        self.sketch_extrude_action.setCheckable(True)
        self.sketch_extrude_action.toggled.connect(lambda checked: self._toggle_interactive_sketch("extrude", checked))
        sketch_mode_group.add_action(self.sketch_extrude_action)

        self.sketch_revolve_action = QAction("Revolve\nPlane", self)
        self.sketch_revolve_action.setCheckable(True)
        self.sketch_revolve_action.toggled.connect(lambda checked: self._toggle_interactive_sketch("revolve", checked))
        sketch_mode_group.add_action(self.sketch_revolve_action)

        numeric_sketch_group = design_tab.add_group("Sketch (typed)")
        numeric_sketch_group.add_action(self._action("Rectangle\n+ Extrude", self.do_sketch_rect_extrude))
        numeric_sketch_group.add_action(self._action("Circle\n+ Extrude", self.do_sketch_circle_extrude))
        numeric_sketch_group.add_action(self._action("Revolve", self.do_sketch_revolve))

        history_group = design_tab.add_group("History")
        undo_action = self._action("Undo", self.undo)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        history_group.add_action(undo_action)
        redo_action = self._action("Redo", self.redo)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        history_group.add_action(redo_action)

        view_group = design_tab.add_group("View")
        view_group.add_action(self._action("Fit All", self.viewport.fit_all))

        sketch_tab = self.ribbon.add_tab("Sketch")
        draw_group = sketch_tab.add_group("Draw")
        for name, label in [("line", "Line"), ("rect", "Rectangle"), ("circle", "Circle")]:
            action = QAction(label, self)
            action.setCheckable(True)
            action.toggled.connect(lambda checked, n=name: self._on_sketch_entity_toggled(n, checked))
            self.sketch_entity_actions[name] = action
            draw_group.add_action(action)

        finish_group = sketch_tab.add_group("Sketch")
        finish_group.add_action(self._action("Close Sketch", self.finish_interactive_sketch))
        finish_group.add_action(self._action("Cancel Sketch", self.cancel_interactive_sketch))

        inspect_tab = self.ribbon.add_tab("Inspect")
        measure_group = inspect_tab.add_group("Measure")
        measure_group.add_action(self._tool_action("measure", "Measure"))

        self.ribbon.set_current_tab(0)

    def _wrap_in_toolbar(self, widget):
        from PySide6.QtWidgets import QToolBar

        tb = QToolBar("Ribbon", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.addWidget(widget)
        return tb

    def select_tool(self):
        for action in self._tool_actions.values():
            if action.isChecked():
                action.setChecked(False)
        if self.interactive_sketch_active:
            self._exit_interactive_sketch()
        self.viewport.clear_selection()
        self.statusBar().showMessage("Ready")

    # -- structure tree -----------------------------------------------
    def _build_structure_tree(self):
        dock = QDockWidget("Structure", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.structure_tree = QTreeWidget(dock)
        self.structure_tree.setHeaderHidden(True)
        self.structure_tree.itemClicked.connect(self._on_structure_item_clicked)
        dock.setWidget(self.structure_tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._refresh_structure_tree()

    def _refresh_structure_tree(self):
        self.structure_tree.clear()
        for obj in self.document.objects:
            item = QTreeWidgetItem([obj.name])
            item.setData(0, Qt.ItemDataRole.UserRole, obj.id)
            self.structure_tree.addTopLevelItem(item)

    def _on_structure_item_clicked(self, item, _column):
        shape_id = item.data(0, Qt.ItemDataRole.UserRole)
        ais = self.viewport.viewer.ais_for(shape_id)
        if ais is None:
            return
        self.viewport.clear_selection()
        self.viewport.viewer.context.AddOrRemoveSelected(ais, True)
        self.viewport.update()

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
            if self.interactive_sketch_active:
                self._exit_interactive_sketch()
            self.active_tool = tool_name
            self.measure_picks = []
            mode, hint = _TOOL_MODES[tool_name]
            self.viewport.clear_selection()
            self.viewport.viewer.set_pick_mode(mode)
            self.statusBar().showMessage(hint)
        elif self.active_tool == tool_name:
            self.active_tool = "select"
            self.measure_picks = []
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
        self._refresh_structure_tree()
        self.statusBar().showMessage(f"Added {obj.name}")
        return obj

    def _sync_viewport(self):
        self.viewport.update()
        self._refresh_structure_tree()

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
        self._sync_viewport()
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

    # -- interactive (click-to-place) sketching ---------------------------
    # Extrude sketches are drawn on the XY plane (normal +Z, matching the
    # extrude direction); Revolve sketches are drawn on the XZ plane
    # (normal +Y, so the profile contains the Z rotation axis -- a profile
    # perpendicular to the axis would sweep zero volume).
    def _current_sketch_normal(self):
        return (0.0, 0.0, 1.0) if self.interactive_sketch_finish_mode == "extrude" else (0.0, 1.0, 0.0)

    def _toggle_interactive_sketch(self, mode: str, checked: bool):
        other = self.sketch_revolve_action if mode == "extrude" else self.sketch_extrude_action
        if checked:
            other.blockSignals(True)
            other.setChecked(False)
            other.blockSignals(False)
            for action in self._tool_actions.values():
                if action.isChecked():
                    action.blockSignals(True)
                    action.setChecked(False)
                    action.blockSignals(False)
            self.active_tool = "select"
            self.viewport.viewer.set_pick_mode(MODE_SOLID)

            self.interactive_sketch_active = True
            self.interactive_sketch_finish_mode = mode
            self.interactive_sketch_points = []
            self.interactive_sketch_profiles = []
            self._interactive_sketch_shape_ids = []
            self.viewport.sketch_mode = True
            normal = self._current_sketch_normal()
            self.viewport.viewer.set_sketch_plane(gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(*normal)))
            self.sketch_entity_actions["rect"].setChecked(True)
            self.ribbon.set_current_tab(1)
            self.statusBar().showMessage(f"Sketch ({mode}): choose Line/Rectangle/Circle, then click points in the viewport")
        elif self.interactive_sketch_active and self.interactive_sketch_finish_mode == mode:
            self._exit_interactive_sketch()

    def _on_sketch_entity_toggled(self, name: str, checked: bool):
        if checked:
            for n, action in self.sketch_entity_actions.items():
                if n != name and action.isChecked():
                    action.blockSignals(True)
                    action.setChecked(False)
                    action.blockSignals(False)
            self.interactive_sketch_tool = name
            self.interactive_sketch_points = []
            self.viewport.viewer.set_preview(None)
        elif self.interactive_sketch_tool == name:
            self.interactive_sketch_tool = None
            self.interactive_sketch_points = []
            self.viewport.viewer.set_preview(None)

    def _on_sketch_hover(self, x: float, y: float, z: float):
        if not self.interactive_sketch_active or not self.interactive_sketch_tool:
            return
        pts = self.interactive_sketch_points + [(x, y, z)]
        preview = None
        try:
            if self.interactive_sketch_tool == "rect" and len(pts) == 2:
                preview = sketch.polygon_profile(sketch.rectangle_points_from_corners(pts[0], pts[1]))
            elif self.interactive_sketch_tool == "circle" and len(pts) == 2:
                radius = sketch.distance(pts[0], pts[1])
                preview = sketch.circle_profile_3d(pts[0], self._current_sketch_normal(), radius)
            elif self.interactive_sketch_tool == "line" and len(pts) >= 2:
                preview = sketch.open_polyline_wire(pts)
        except Exception:
            preview = None  # degenerate in-progress geometry (e.g. zero-size); just skip the preview
        self.viewport.viewer.set_preview(preview)
        self._sync_viewport()

    def _on_sketch_clicked(self, x: float, y: float, z: float):
        if not self.interactive_sketch_active or not self.interactive_sketch_tool:
            return
        pts = self.interactive_sketch_points
        pts.append((x, y, z))
        tool = self.interactive_sketch_tool
        try:
            if tool == "rect" and len(pts) == 2:
                self._finalize_sketch_profile(sketch.polygon_profile(sketch.rectangle_points_from_corners(pts[0], pts[1])))
            elif tool == "circle" and len(pts) == 2:
                radius = sketch.distance(pts[0], pts[1])
                self._finalize_sketch_profile(sketch.circle_profile_3d(pts[0], self._current_sketch_normal(), radius))
            elif tool == "line":
                self.statusBar().showMessage(f"Sketch: {len(pts)} point(s) placed — double-click to close the polygon")
        except Exception as exc:
            QMessageBox.warning(self, "Sketch", str(exc))
            self.interactive_sketch_points = []

    def _on_sketch_finish_entity(self):
        if not self.interactive_sketch_active or self.interactive_sketch_tool != "line":
            return
        pts = self.interactive_sketch_points
        if len(pts) < 3:
            QMessageBox.information(self, "Sketch", "A polygon needs at least 3 points.")
            return
        try:
            face = sketch.polygon_profile(pts)
        except Exception as exc:
            QMessageBox.warning(self, "Sketch", str(exc))
            return
        self._finalize_sketch_profile(face)

    def _finalize_sketch_profile(self, face):
        self.interactive_sketch_profiles.append(face)
        temp_id = _SKETCH_TEMP_ID_BASE - len(self.interactive_sketch_profiles)
        self._interactive_sketch_shape_ids.append(temp_id)
        self.viewport.viewer.display_shape(temp_id, face)
        self.viewport.viewer.set_preview(None)
        self.interactive_sketch_points = []
        self._sync_viewport()
        self.statusBar().showMessage(
            f"Sketch: {len(self.interactive_sketch_profiles)} profile(s) placed — add more or Finish Sketch"
        )

    def _exit_interactive_sketch(self):
        for temp_id in self._interactive_sketch_shape_ids:
            self.viewport.viewer.remove_shape(temp_id)
        self._interactive_sketch_shape_ids = []
        self.viewport.viewer.set_preview(None)
        self.interactive_sketch_active = False
        self.interactive_sketch_finish_mode = None
        self.interactive_sketch_tool = None
        self.interactive_sketch_points = []
        self.interactive_sketch_profiles = []
        self.viewport.sketch_mode = False
        self.viewport.viewer.set_pick_mode(MODE_SOLID)
        for action in list(self.sketch_entity_actions.values()) + [self.sketch_extrude_action, self.sketch_revolve_action]:
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
        self.ribbon.set_current_tab(0)
        self._sync_viewport()
        self.statusBar().showMessage("Ready")

    def cancel_interactive_sketch(self):
        if self.interactive_sketch_active:
            self._exit_interactive_sketch()

    def finish_interactive_sketch(self):
        if not self.interactive_sketch_active:
            return
        if not self.interactive_sketch_profiles:
            QMessageBox.information(self, "Finish Sketch", "Sketch at least one closed profile first (Rectangle/Circle, or Line + double-click).")
            return
        mode = self.interactive_sketch_finish_mode
        if mode == "extrude":
            height, ok = QInputDialog.getDouble(self, "Extrude", "Height:", 2.0, -1000.0, 1000.0, 3)
            if not ok:
                return
            op, name = (lambda face: sketch.extrude(face, height)), "SketchExtrude"
        else:
            angle, ok = QInputDialog.getDouble(self, "Revolve", "Angle (degrees):", 360.0, 0.001, 360.0, 2)
            if not ok:
                return
            op, name = (lambda face: sketch.revolve(face, angle)), "SketchRevolve"

        profiles = list(self.interactive_sketch_profiles)
        self.document.snapshot()
        self._exit_interactive_sketch()
        for face in profiles:
            try:
                solid = op(face)
            except Exception as exc:
                QMessageBox.warning(self, "Sketch finish failed", str(exc))
                continue
            self._add_to_scene(solid, name=name)

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
        self._sync_viewport()
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
        self._sync_viewport()
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
        self._sync_viewport()

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
        elif self.active_tool == "measure":
            if shape.ShapeType() != TopAbs_FACE:
                return
            self._on_measure_picked(shape)

    def _on_measure_picked(self, face):
        self.measure_picks.append(face)
        if len(self.measure_picks) == 1:
            self.statusBar().showMessage(
                f"Measure: {measure.describe(face)} — click another face for the distance between them"
            )
        else:
            a, b = self.measure_picks
            self.measure_picks = []
            try:
                distance = measure.distance_between(a, b)
            except Exception as exc:
                QMessageBox.warning(self, "Measure failed", str(exc))
                return
            self.statusBar().showMessage(f"Measure: distance between faces = {distance:.4g}")

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
        self._sync_viewport()
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
        self._sync_viewport()
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
