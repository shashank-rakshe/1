"""Main application window: toolbar-driven direct-modeling CAD shell."""

from PySide6.QtWidgets import (
    QMainWindow,
    QToolBar,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QStatusBar,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt

from dcad.kernel.document import Document
from dcad.kernel import primitives, booleans, direct_edit, io_step
from dcad.viewport.viewport_widget import ViewportWidget
from dcad.viewport.occt_viewer import MODE_SOLID, MODE_FACE
from OCP.TopAbs import TopAbs_FACE


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("dcad — direct-modeling CAD")
        self.resize(1200, 800)

        self.document = Document()
        self.viewport = ViewportWidget(self)
        self.setCentralWidget(self.viewport)
        self.viewport.picked.connect(self._on_picked)

        self.pull_tool_active = False

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
        tb.addAction(self._action("Union", self.do_union))
        tb.addAction(self._action("Subtract", self.do_subtract))
        tb.addAction(self._action("Intersect", self.do_intersect))
        tb.addSeparator()

        self.pull_action = QAction("Pull/Push", self)
        self.pull_action.setCheckable(True)
        self.pull_action.toggled.connect(self._toggle_pull_tool)
        tb.addAction(self.pull_action)
        tb.addSeparator()

        tb.addAction(self._action("Open STEP...", self.open_step))
        tb.addAction(self._action("Save STEP...", self.save_step))
        tb.addSeparator()
        tb.addAction(self._action("Fit All", self.viewport.fit_all))

    def _action(self, label: str, slot) -> QAction:
        action = QAction(label, self)
        action.triggered.connect(slot)
        return action

    # -- primitives ----------------------------------------------------
    def add_box(self):
        shape = primitives.make_box(2, 2, 2)
        self._add_to_scene(shape)

    def add_cylinder(self):
        shape = primitives.make_cylinder(1, 2)
        self._add_to_scene(shape)

    def add_sphere(self):
        shape = primitives.make_sphere(1)
        self._add_to_scene(shape)

    def _add_to_scene(self, shape):
        obj = self.document.add(shape)
        self.viewport.viewer.display_shape(obj.id, shape)
        self.viewport.fit_all()
        self.statusBar().showMessage(f"Added {obj.name}")

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

    # -- direct-modeling pull/push ------------------------------------
    def _toggle_pull_tool(self, checked: bool):
        self.pull_tool_active = checked
        self.viewport.clear_selection()
        if checked:
            self.viewport.viewer.set_pick_mode(MODE_FACE)
            self.statusBar().showMessage("Pull/Push: click a face")
        else:
            self.viewport.viewer.set_pick_mode(MODE_SOLID)
            self.statusBar().showMessage("Ready")

    def _on_picked(self, shape, owner_id: int):
        if not self.pull_tool_active or shape is None or owner_id < 0:
            return
        if shape.ShapeType() != TopAbs_FACE:
            return
        obj = self.document.get(owner_id)
        if obj is None:
            return
        distance, ok = QInputDialog.getDouble(
            self, "Pull/Push face", "Distance (positive = pull out, negative = push in):",
            1.0, -1000.0, 1000.0, 3,
        )
        if not ok or distance == 0:
            return
        try:
            new_shape = direct_edit.pull_face(obj.shape, shape, distance)
        except Exception as exc:
            QMessageBox.warning(self, "Pull/Push failed", str(exc))
            return
        self.document.replace_shape(obj, new_shape)
        self.viewport.viewer.redisplay_shape(obj.id, new_shape)
        self.viewport.update()
        self.statusBar().showMessage(f"Pulled {obj.name} by {distance:g}")

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
