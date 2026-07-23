"""Main application window: toolbar-driven direct-modeling CAD shell."""

from pathlib import Path

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
    QProgressDialog,
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt

from dcad.kernel.document import Document
from dcad.kernel import primitives, booleans, direct_edit, io_step, transform, fillet, project_io, sketch, measure, repair, prepare, assembly, detail
from dcad.viewport.viewport_widget import ViewportWidget
from dcad.viewport.occt_viewer import MODE_SOLID, MODE_FACE, MODE_EDGE
from dcad.ui.ribbon import RibbonBar
from dcad.ui.theme import STYLESHEET
from dcad.ui import icons
from dcad.ui.workers import StepImportWorker
from dcad.ui.detail_view import DetailViewDialog
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
    "fill": (MODE_FACE, "Fill: click a face to remove and heal"),
    "align": (MODE_FACE, "Align: click the face to move, then click the face to align it to"),
    "orient": (MODE_EDGE, "Orient: click the edge to rotate, then click the edge to match its direction"),
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
        self.viewport.right_clicked.connect(self._show_context_menu)

        self.active_tool = "select"
        self._tool_actions = {}
        self.measure_picks = []
        self.align_picks = []  # [(DocObject, TopoDS_Face), ...] -- moving pick first, stationary second
        self.orient_picks = []  # [(DocObject, TopoDS_Edge), ...] -- moving pick first, target pick second
        self._anchored_ids = set()  # SpaceClaim's Assembly > Anchor: locks a part in place

        self.interactive_sketch_active = False
        self.interactive_sketch_finish_mode = None  # "extrude" | "revolve"
        self.interactive_sketch_tool = None  # "line" | "rect" | "circle"
        self.interactive_sketch_points = []
        self.interactive_sketch_profiles = []
        self._interactive_sketch_shape_ids = []
        self.sketch_entity_actions = {}
        self._polygon_sides = 6

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
        file_menu.addAction(self._action("Open STEP...", self.open_step, "file"))
        file_menu.addAction(self._action("Save STEP...", self.save_step, "file"))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Open Project...", self.open_project, "file"))
        file_menu.addAction(self._action("Save Project...", self.save_project, "file"))
        self.ribbon.file_button.setMenu(file_menu)

        design_tab = self.ribbon.add_tab("Design")

        select_group = design_tab.add_group("Select")
        select_group.add_action(self._action("Select", self.select_tool, "select"))

        create_group = design_tab.add_group("Create")
        create_group.add_action(self._action("Box", self.add_box, "box"))
        create_group.add_action(self._action("Cylinder", self.add_cylinder, "cylinder"))
        create_group.add_action(self._action("Sphere", self.add_sphere, "sphere"))

        edit_group = design_tab.add_group("Edit")
        edit_group.add_action(self._tool_action("pull", "Pull", "pull"))
        edit_group.add_action(self._action("Move", self.do_move, "move"))
        edit_group.add_action(self._action("Rotate", self.do_rotate, "rotate"))
        edit_group.add_action(self._action("Copy", self.do_copy, "copy"))
        edit_group.add_action(self._action("Revolve", self.do_revolve_surface, "revolve"))

        combine_group = design_tab.add_group("Combine")
        combine_group.add_action(self._action("Merge", self.do_union, "merge"))
        combine_group.add_action(self._action("Subtract", self.do_subtract, "subtract"))
        combine_group.add_action(self._action("Intersect", self.do_intersect, "intersect"))

        construct_group = design_tab.add_group("Construct")
        construct_group.add_action(self._tool_action("fillet", "Fillet", "fillet"))
        construct_group.add_action(self._tool_action("chamfer", "Chamfer", "chamfer"))

        sketch_mode_group = design_tab.add_group("Sketch Mode")
        self.sketch_extrude_action = QAction("Extrude\nPlane", self)
        self.sketch_extrude_action.setIcon(icons.get("sketch_extrude_plane"))
        self.sketch_extrude_action.setCheckable(True)
        self.sketch_extrude_action.toggled.connect(lambda checked: self._toggle_interactive_sketch("extrude", checked))
        sketch_mode_group.add_action(self.sketch_extrude_action)

        self.sketch_revolve_action = QAction("Revolve\nPlane", self)
        self.sketch_revolve_action.setIcon(icons.get("sketch_revolve_plane"))
        self.sketch_revolve_action.setCheckable(True)
        self.sketch_revolve_action.toggled.connect(lambda checked: self._toggle_interactive_sketch("revolve", checked))
        sketch_mode_group.add_action(self.sketch_revolve_action)

        numeric_sketch_group = design_tab.add_group("Sketch (typed)")
        numeric_sketch_group.add_action(self._action("Rectangle\n+ Extrude", self.do_sketch_rect_extrude, "rect"))
        numeric_sketch_group.add_action(self._action("Circle\n+ Extrude", self.do_sketch_circle_extrude, "circle"))
        numeric_sketch_group.add_action(self._action("Revolve", self.do_sketch_revolve, "revolve"))

        history_group = design_tab.add_group("History")
        undo_action = self._action("Undo", self.undo, "undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        history_group.add_action(undo_action)
        redo_action = self._action("Redo", self.redo, "redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        history_group.add_action(redo_action)

        view_group = design_tab.add_group("View")
        view_group.add_action(self._action("Fit All", self.viewport.fit_all, "fit_all"))

        sketch_tab = self.ribbon.add_tab("Sketch")
        draw_group = sketch_tab.add_group("Draw")
        for name, label in [
            ("line", "Line"),
            ("rect", "Rectangle"),
            ("circle", "Circle"),
            ("polygon", "Polygon"),
            ("ellipse", "Ellipse"),
            ("circle3pt", "3-Point\nCircle"),
            ("arc3pt", "3-Point\nArc"),
        ]:
            action = QAction(label, self)
            action.setIcon(icons.get(name))
            action.setCheckable(True)
            action.toggled.connect(lambda checked, n=name: self._on_sketch_entity_toggled(n, checked))
            self.sketch_entity_actions[name] = action
            draw_group.add_action(action)

        finish_group = sketch_tab.add_group("Sketch")
        finish_group.add_action(self._action("Close Sketch", self.finish_interactive_sketch, "check"))
        finish_group.add_action(self._action("Cancel Sketch", self.cancel_interactive_sketch, "cancel"))

        assembly_tab = self.ribbon.add_tab("Assembly")
        align_group = assembly_tab.add_group("Align")
        align_group.add_action(self._tool_action("align", "Align", "align"))
        align_group.add_action(self._tool_action("orient", "Orient", "orient"))
        fix_group_asm = assembly_tab.add_group("Fix")
        fix_group_asm.add_action(self._action("Anchor", self.toggle_anchor, "anchor"))

        detail_tab = self.ribbon.add_tab("Detail")
        views_group = detail_tab.add_group("Views")
        views_group.add_action(self._action("Front", lambda: self.do_detail_view("front"), "view_front"))
        views_group.add_action(self._action("Top", lambda: self.do_detail_view("top"), "view_top"))
        views_group.add_action(self._action("Right", lambda: self.do_detail_view("right"), "view_right"))
        views_group.add_action(self._action("Isometric", lambda: self.do_detail_view("isometric"), "view_iso"))

        inspect_tab = self.ribbon.add_tab("Inspect")
        measure_group = inspect_tab.add_group("Measure")
        measure_group.add_action(self._tool_action("measure", "Measure", "measure"))

        repair_tab = self.ribbon.add_tab("Repair")
        solidify_group = repair_tab.add_group("Solidify")
        solidify_group.add_action(self._action("Stitch", self.do_stitch, "stitch"))
        fix_group = repair_tab.add_group("Fix")
        fix_group.add_action(self._tool_action("fill", "Fill", "fill"))
        adjust_group = repair_tab.add_group("Adjust")
        adjust_group.add_action(self._action("Merge\nFaces", self.do_merge_faces, "merge_faces"))

        prepare_tab = self.ribbon.add_tab("Prepare")
        prepare_group = prepare_tab.add_group("Prepare")
        prepare_group.add_action(self._action("Interference", self.do_check_interference, "interference"))
        prepare_group.add_action(self._action("Enclosure", self.do_enclosure, "enclosure"))
        prepare_group.add_action(self._action("Share\nTopology", self.do_share_topology, "share_topology"))

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

    def select_all(self):
        self.viewport.clear_selection()
        for obj in self.document.objects:
            ais = self.viewport.viewer.ais_for(obj.id)
            if ais is not None:
                self.viewport.viewer.context.AddOrRemoveSelected(ais, False)
        self.viewport.update()

    def delete_selected(self):
        ids = self.viewport.selected_shape_ids()
        if not ids:
            return
        self.document.snapshot()
        for shape_id in ids:
            obj = self.document.get(shape_id)
            if obj is not None:
                self.viewport.viewer.remove_shape(shape_id)
                self.document.remove(obj)
                self._anchored_ids.discard(shape_id)
        self._sync_viewport()
        self.statusBar().showMessage(f"Deleted {len(ids)} object(s)")

    # -- assembly (Align, Anchor) ------------------------------------------
    def _check_not_anchored(self, obj) -> bool:
        """SpaceClaim's Anchor fixes a component's position -- guard the
        direct-modeling tools that would move it (Move/Rotate/Align)."""
        if obj.id in self._anchored_ids:
            QMessageBox.information(
                self, "Anchored", f"{obj.name} is anchored and can't be moved. Toggle Anchor to release it."
            )
            return False
        return True

    def toggle_anchor(self):
        ids = self.viewport.selected_shape_ids()
        if not ids:
            QMessageBox.information(self, "Anchor", "Select one or more solids first.")
            return
        for shape_id in ids:
            if shape_id in self._anchored_ids:
                self._anchored_ids.discard(shape_id)
            else:
                self._anchored_ids.add(shape_id)
        self._refresh_structure_tree()
        names = [self.document.get(i).name for i in ids if self.document.get(i) is not None]
        self.statusBar().showMessage(f"Toggled anchor for {', '.join(names)}")

    # -- right-click context menu (SpaceClaim's Select menu) --------------
    def _show_context_menu(self, global_pos):
        self._build_context_menu().exec(global_pos)

    def _build_context_menu(self) -> QMenu:
        ids = self.viewport.selected_shape_ids()
        menu = QMenu(self)

        if len(ids) == 1:
            obj = self.document.get(ids[0])
            menu.addAction(self._action("Move", self.do_move, "move"))
            menu.addAction(self._action("Rotate", self.do_rotate, "rotate"))
            menu.addAction(self._action("Copy", self.do_copy, "copy"))
            if obj is not None and obj.shape.ShapeType() == TopAbs_FACE:
                menu.addAction(self._action("Revolve", self.do_revolve_surface, "revolve"))
            menu.addAction(self._action("Merge Faces", self.do_merge_faces, "merge_faces"))
            menu.addSeparator()
        elif len(ids) == 2:
            menu.addAction(self._action("Merge", self.do_union, "merge"))
            menu.addAction(self._action("Subtract", self.do_subtract, "subtract"))
            menu.addAction(self._action("Intersect", self.do_intersect, "intersect"))
            menu.addAction(self._action("Stitch", self.do_stitch, "stitch"))
            menu.addAction(self._action("Share Topology", self.do_share_topology, "share_topology"))
            menu.addSeparator()
        elif len(ids) > 2:
            menu.addAction(self._action("Stitch", self.do_stitch, "stitch"))
            menu.addAction(self._action("Share Topology", self.do_share_topology, "share_topology"))
            menu.addSeparator()

        if ids:
            anchor_label = "Unanchor" if all(i in self._anchored_ids for i in ids) else "Anchor"
            menu.addAction(self._action(anchor_label, self.toggle_anchor, "anchor"))
            menu.addAction(self._action("Delete", self.delete_selected, "cancel"))
            menu.addSeparator()

        menu.addAction(self._action("Select All", self.select_all, "select"))
        menu.addAction(self._action("Deselect All", self.viewport.clear_selection))
        menu.addAction(self._action("Fit All", self.viewport.fit_all, "fit_all"))
        return menu

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
            label = f"{obj.name} (Anchored)" if obj.id in self._anchored_ids else obj.name
            item = QTreeWidgetItem([label])
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

    def _action(self, label: str, slot, icon: str | None = None) -> QAction:
        action = QAction(label, self)
        if icon:
            action.setIcon(icons.get(icon))
        action.triggered.connect(slot)
        return action

    def _tool_action(self, tool_name: str, label: str, icon: str | None = None) -> QAction:
        action = QAction(label, self)
        if icon:
            action.setIcon(icons.get(icon))
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
            self.align_picks = []
            self.orient_picks = []
            mode, hint = _TOOL_MODES[tool_name]
            self.viewport.clear_selection()
            self.viewport.viewer.set_pick_mode(mode)
            self.statusBar().showMessage(hint)
        elif self.active_tool == tool_name:
            self.active_tool = "select"
            self.measure_picks = []
            self.align_picks = []
            self.orient_picks = []
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

    def _add_many_to_scene(self, shapes, name_prefix: str = ""):
        """Bulk version of `_add_to_scene`: adds every shape, then does a
        single fit_all()/structure-tree rebuild at the end instead of one
        per shape -- rebuilding the tree per part would be O(n^2) for a
        big assembly import."""
        objs = []
        for i, shape in enumerate(shapes):
            name = f"{name_prefix}{i + 1}" if name_prefix else ""
            obj = self.document.add(shape, name=name)
            self.viewport.viewer.display_shape(obj.id, shape)
            objs.append(obj)
        self.viewport.fit_all()
        self._refresh_structure_tree()
        self.statusBar().showMessage(f"Added {len(objs)} part(s)")
        return objs

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

    # -- repair (Stitch, Fill, Merge Faces) -------------------------------
    def _selected_multiple(self, min_count: int = 2):
        ids = self.viewport.selected_shape_ids()
        if len(ids) < min_count:
            QMessageBox.information(self, "Select solids", f"Select at least {min_count} solids first.")
            return None
        objs = [self.document.get(i) for i in ids]
        if any(o is None for o in objs):
            return None
        return objs

    def do_stitch(self):
        objs = self._selected_multiple(2)
        if objs is None:
            return
        try:
            result = repair.stitch([o.shape for o in objs])
        except Exception as exc:
            QMessageBox.warning(self, "Stitch failed", str(exc))
            return
        self.document.snapshot()
        for obj in objs:
            self.viewport.viewer.remove_shape(obj.id)
            self.document.remove(obj)
        self._add_to_scene(result, name="Stitched")

    def do_merge_faces(self):
        obj = self._selected_single()
        if obj is None:
            return
        try:
            new_shape = repair.merge_faces(obj.shape)
        except Exception as exc:
            QMessageBox.warning(self, "Merge Faces failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self._sync_viewport()
        self.statusBar().showMessage(f"Merged faces on {obj.name}")

    # -- prepare (Interference, Enclosure, Share Topology) ----------------
    def do_check_interference(self):
        if len(self.document.objects) < 2:
            QMessageBox.information(self, "Interference", "Need at least two solids in the document.")
            return
        objs = self.document.objects
        hits = prepare.check_interference([o.shape for o in objs])
        if not hits:
            QMessageBox.information(self, "Interference", "No interference found.")
            return
        lines = [f"{objs[i].name} ↔ {objs[j].name}: overlap volume {v:.4g}" for i, j, v in hits]
        QMessageBox.information(self, "Interference", "\n".join(lines))

    def do_enclosure(self):
        ids = self.viewport.selected_shape_ids()
        objs = [self.document.get(i) for i in ids] if ids else list(self.document.objects)
        if not objs:
            QMessageBox.information(self, "Enclosure", "Nothing to build an enclosure around.")
            return
        margin, ok = QInputDialog.getDouble(self, "Enclosure", "Margin:", 5.0, 0.001, 10000.0, 3)
        if not ok:
            return
        try:
            enclosure = prepare.make_enclosure([o.shape for o in objs], margin)
        except Exception as exc:
            QMessageBox.warning(self, "Enclosure failed", str(exc))
            return
        self.document.snapshot()
        self._add_to_scene(enclosure, name="Enclosure")

    def do_share_topology(self):
        objs = self._selected_multiple(2)
        if objs is None:
            return
        try:
            result = prepare.share_topology([o.shape for o in objs])
        except Exception as exc:
            QMessageBox.warning(self, "Share Topology failed", str(exc))
            return
        solids = prepare.explode_solids(result)
        self.document.snapshot()
        for obj in objs:
            self.viewport.viewer.remove_shape(obj.id)
            self.document.remove(obj)
        for solid in solids:
            self._add_to_scene(solid, name="Shared")
        self.statusBar().showMessage(f"Share Topology: {len(solids)} solid(s) now share topology")

    # -- detail (2D hidden-line-removed drawing views) ---------------------
    def do_detail_view(self, view: str):
        """SpaceClaim's Detail tab: place an orthographic/isometric
        drawing view of the model, with hidden lines shown dashed. This
        opens a standalone window per view rather than placing views on a
        shared drawing sheet with a title block -- that sheet-layout/
        dimensioning layer isn't built."""
        if not self.document.objects:
            QMessageBox.information(self, "Detail", "The document is empty.")
            return
        shapes = [o.shape for o in self.document.objects]
        try:
            visible, hidden = detail.project_view(shapes, view)
        except Exception as exc:
            QMessageBox.warning(self, "Detail view failed", str(exc))
            return
        dialog = DetailViewDialog(f"{view.capitalize()} View", visible, hidden, self)
        self._detail_dialogs = getattr(self, "_detail_dialogs", [])
        self._detail_dialogs.append(dialog)
        dialog.show()
        self.statusBar().showMessage(f"{view.capitalize()} view: {len(visible)} visible, {len(hidden)} hidden edges")

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

    # tool name -> number of points needed before it self-finalizes (None = line/open-ended, closed via double-click)
    _SKETCH_TOOL_POINT_COUNTS = {
        "rect": 2, "circle": 2, "polygon": 2, "ellipse": 3, "circle3pt": 3, "arc3pt": 3,
    }

    def _build_sketch_preview(self, tool: str, pts: list):
        normal = self._current_sketch_normal()
        if tool == "rect" and len(pts) == 2:
            return sketch.polygon_profile(sketch.rectangle_points_from_corners(pts[0], pts[1]))
        if tool == "circle" and len(pts) == 2:
            return sketch.circle_profile_3d(pts[0], normal, sketch.distance(pts[0], pts[1]))
        if tool == "polygon" and len(pts) == 2:
            return sketch.regular_polygon_profile(pts[0], pts[1], normal, self._polygon_sides)
        if tool == "ellipse" and len(pts) == 3:
            return sketch.ellipse_profile_3d(pts[0], pts[1], sketch.distance(pts[0], pts[2]), normal)
        if tool == "circle3pt" and len(pts) == 3:
            return sketch.three_point_circle_profile(pts[0], pts[1], pts[2])
        if tool == "arc3pt" and len(pts) == 3:
            return sketch.three_point_arc_segment_profile(pts[0], pts[1], pts[2])
        if tool == "line" and len(pts) >= 2:
            return sketch.open_polyline_wire(pts)
        return None

    def _on_sketch_hover(self, x: float, y: float, z: float):
        if not self.interactive_sketch_active or not self.interactive_sketch_tool:
            return
        pts = self.interactive_sketch_points + [(x, y, z)]
        try:
            preview = self._build_sketch_preview(self.interactive_sketch_tool, pts)
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
        needed = self._SKETCH_TOOL_POINT_COUNTS.get(tool)

        if tool == "polygon" and len(pts) == 2:
            sides, ok = QInputDialog.getInt(self, "Polygon", "Number of sides:", self._polygon_sides, 3, 32)
            if ok:
                self._polygon_sides = sides

        if needed is not None and len(pts) == needed:
            try:
                self._finalize_sketch_profile(self._build_sketch_preview(tool, pts))
            except Exception as exc:
                QMessageBox.warning(self, "Sketch", str(exc))
                self.interactive_sketch_points = []
        elif tool == "line":
            self.statusBar().showMessage(f"Sketch: {len(pts)} point(s) placed — double-click to close the polygon")

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
        # Matches SpaceClaim's real sketch workflow: closing a sketch turns
        # each closed profile into a flat, zero-thickness Surface object --
        # it does NOT extrude/revolve immediately. Use Pull on a Surface's
        # face to thicken it into a solid, or the Revolve tool to spin it
        # into one (see do_pull_or_thicken / do_revolve_surface).
        if not self.interactive_sketch_active:
            return
        if not self.interactive_sketch_profiles:
            QMessageBox.information(self, "Finish Sketch", "Sketch at least one closed profile first (Rectangle/Circle, or Line + double-click).")
            return
        profiles = list(self.interactive_sketch_profiles)
        self.document.snapshot()
        self._exit_interactive_sketch()
        for face in profiles:
            self._add_to_scene(face, name="Surface")

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
        if not self._check_not_anchored(obj):
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
        if not self._check_not_anchored(obj):
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

    def do_revolve_surface(self):
        """Spins a standalone Surface (a flat, closed sketch profile that
        hasn't been Pulled into a solid yet) about the Z axis through the
        origin -- the other way (besides Pull) to turn a Surface solid."""
        obj = self._selected_single()
        if obj is None:
            return
        if obj.shape.ShapeType() != TopAbs_FACE:
            QMessageBox.information(self, "Revolve", "Select a Surface (a flat sketch profile, not yet a solid) to revolve.")
            return
        angle, ok = QInputDialog.getDouble(self, "Revolve", "Angle (degrees, about Z axis through origin):", 360.0, 0.001, 360.0, 2)
        if not ok:
            return
        try:
            new_shape = sketch.revolve(obj.shape, angle)
        except Exception as exc:
            QMessageBox.warning(self, "Revolve failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self._sync_viewport()
        self.statusBar().showMessage(f"Revolved {obj.name} by {angle:g} deg")

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
        elif self.active_tool == "fill":
            if shape.ShapeType() != TopAbs_FACE:
                return
            self._apply_fill(obj, shape)
        elif self.active_tool == "align":
            if shape.ShapeType() != TopAbs_FACE:
                return
            self._on_align_picked(obj, shape)
        elif self.active_tool == "orient":
            if shape.ShapeType() != TopAbs_EDGE:
                return
            self._on_orient_picked(obj, shape)

    def _on_align_picked(self, obj, face):
        """SpaceClaim's Assembly > Align: click the face to move, then
        click the face it should become coincident with."""
        self.align_picks.append((obj, face))
        if len(self.align_picks) == 1:
            self.statusBar().showMessage(
                f"Align: {obj.name} face selected to move — click the face to align it to"
            )
            return
        (moving_obj, moving_face), (stationary_obj, stationary_face) = self.align_picks
        self.align_picks = []
        if not self._check_not_anchored(moving_obj):
            return
        try:
            new_shape = assembly.align_faces(moving_obj.shape, moving_face, stationary_face)
        except Exception as exc:
            QMessageBox.warning(self, "Align failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(moving_obj, new_shape)
        self.viewport.viewer.redisplay_shape(moving_obj.id, new_shape)
        self._sync_viewport()
        self.statusBar().showMessage(f"Aligned {moving_obj.name} to {stationary_obj.name}")

    def _on_orient_picked(self, obj, edge):
        """SpaceClaim's Assembly > Orient: the follow-up to Align that
        fixes rotation about an already-shared axis/plane -- click the
        edge to rotate, then the edge it should point the same way as."""
        self.orient_picks.append((obj, edge))
        if len(self.orient_picks) == 1:
            self.statusBar().showMessage(
                f"Orient: {obj.name} edge selected to rotate — click the edge to match its direction to"
            )
            return
        (moving_obj, moving_edge), (target_obj, target_edge) = self.orient_picks
        self.orient_picks = []
        if not self._check_not_anchored(moving_obj):
            return
        try:
            new_shape = assembly.orient_edges(moving_obj.shape, moving_edge, target_edge)
        except Exception as exc:
            QMessageBox.warning(self, "Orient failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(moving_obj, new_shape)
        self.viewport.viewer.redisplay_shape(moving_obj.id, new_shape)
        self._sync_viewport()
        self.statusBar().showMessage(f"Oriented {moving_obj.name} to match {target_obj.name}")

    def _apply_fill(self, obj, face):
        try:
            new_shape = repair.fill_faces(obj.shape, [face])
        except Exception as exc:
            QMessageBox.warning(self, "Fill failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self._sync_viewport()
        self.statusBar().showMessage(f"Filled a face on {obj.name}")

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
        is_bare_surface = obj.shape.ShapeType() == TopAbs_FACE
        prompt = (
            "Thickness (the surface becomes a solid this thick):"
            if is_bare_surface
            else "Distance (positive = pull out, negative = push in):"
        )
        distance, ok = QInputDialog.getDouble(self, "Pull/Push face", prompt, 1.0, -1000.0, 1000.0, 3)
        if not ok or distance == 0:
            return
        try:
            if is_bare_surface:
                # Pulling a standalone Surface thickens it into a solid
                # (SpaceClaim's real behavior), rather than fusing/cutting
                # against an existing solid.
                new_shape = sketch.extrude(face, distance)
            else:
                new_shape = direct_edit.pull_face(obj.shape, face, distance)
        except Exception as exc:
            QMessageBox.warning(self, "Pull/Push failed", str(exc))
            return
        self.document.snapshot()
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self._sync_viewport()
        verb = "Thickened" if is_bare_surface else "Pulled"
        self.statusBar().showMessage(f"{verb} {obj.name} by {distance:g}")

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

        progress = QProgressDialog("Importing STEP file...", "", 0, 0, self)
        progress.setWindowTitle("Open STEP")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        # Reading + tessellating a big assembly can take a while; doing it
        # on a worker thread keeps the UI (and this progress dialog) alive
        # instead of freezing for the duration of the import.
        worker = StepImportWorker(path, self)

        def on_succeeded(shapes):
            progress.close()
            self.document.snapshot()
            self._add_many_to_scene(shapes, name_prefix=Path(path).stem + "_")
            self._step_import_worker = None

        def on_failed(message):
            progress.close()
            QMessageBox.warning(self, "Open failed", message)
            self._step_import_worker = None

        worker.succeeded.connect(on_succeeded)
        worker.failed.connect(on_failed)
        self._step_import_worker = worker  # keep alive for the thread's duration
        worker.start()

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
