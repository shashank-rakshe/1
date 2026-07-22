"""Qt widget embedding the OCCT viewer, with mouse-driven camera navigation
and face picking for the direct-modeling tools."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QMouseEvent, QWheelEvent, QResizeEvent, QPaintEvent

from dcad.viewport.occt_viewer import OcctViewer


class ViewportWidget(QWidget):
    picked = Signal(object, int)  # (TopoDS_Shape, owning shape_id) or (None, -1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_PaintOnScreen, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 200)

        self.viewer = OcctViewer()
        self._initialized = False
        self._last_pos = None
        self._drag_mode = None  # None | 'rotate' | 'pan'
        self._press_pos = None

    def paintEngine(self):
        return None  # Qt must not paint over the native OpenGL surface.

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initialized:
            self.viewer.bind_window(int(self.winId()), self.width(), self.height())
            self._initialized = True

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self._initialized:
            self.viewer.resize()

    def paintEvent(self, event: QPaintEvent):
        if self._initialized:
            self.viewer.redraw()

    def fit_all(self):
        if self._initialized:
            self.viewer.fit_all()
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        self._last_pos = pos
        self._press_pos = pos
        if event.button() == Qt.MouseButton.MiddleButton or event.button() == Qt.MouseButton.RightButton:
            self._drag_mode = "pan"
        elif event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = "rotate"
            self.viewer.view.StartRotation(pos.x(), pos.y())

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._initialized:
            return
        pos = event.position().toPoint()
        if self._drag_mode == "rotate":
            self.viewer.view.Rotation(pos.x(), pos.y())
            self.update()
        elif self._drag_mode == "pan" and self._last_pos is not None:
            dx = pos.x() - self._last_pos.x()
            dy = pos.y() - self._last_pos.y()
            self.viewer.view.Pan(dx, -dy)
            self.update()
        else:
            self.viewer.context.MoveTo(pos.x(), pos.y(), self.viewer.view, True)
            self.update()
        self._last_pos = pos

    def mouseReleaseEvent(self, event: QMouseEvent):
        was_click = (
            self._press_pos is not None
            and (event.position().toPoint() - self._press_pos).manhattanLength() < 4
        )
        self._drag_mode = None
        if event.button() == Qt.MouseButton.LeftButton and was_click and self._initialized:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.viewer.context.ShiftSelect(True)
            else:
                self.viewer.context.Select(True)
            self._emit_pick()
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        if not self._initialized:
            return
        factor = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
        self.viewer.view.SetZoom(factor)
        self.update()

    def selected_shape_ids(self) -> list[int]:
        context = self.viewer.context
        return [
            shape_id
            for shape_id, ais in self.viewer._ais_by_shape_id.items()
            if context.IsSelected(ais)
        ]

    def clear_selection(self):
        self.viewer.context.ClearSelected(True)

    def _emit_pick(self):
        context = self.viewer.context
        if not context.HasSelectedShape():
            self.picked.emit(None, -1)
            return
        shape = context.SelectedShape()
        for shape_id, ais in self.viewer._ais_by_shape_id.items():
            if context.IsSelected(ais):
                self.picked.emit(shape, shape_id)
                return
        self.picked.emit(None, -1)
