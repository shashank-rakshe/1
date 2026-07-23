"""2D drawing-view window: renders a hidden-line-removed projection (see
kernel/detail.py) with visible edges solid and hidden edges dashed --
SpaceClaim's Detail tab.

Real SpaceClaim places multiple views on a shared drawing sheet with
borders/title blocks; this is a deliberate simplification -- one
independent window per requested view, no sheet layout or dimensioning
yet."""

from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtCore import Qt, QPointF


class DetailViewWidget(QWidget):
    def __init__(self, visible_segments, hidden_segments, parent=None):
        super().__init__(parent)
        self.visible_segments = visible_segments
        self.hidden_segments = hidden_segments
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background-color: white;")

    def _bounds(self):
        points = [p for seg in (self.visible_segments + self.hidden_segments) for p in seg]
        if not points:
            return None
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return min(xs), max(xs), min(ys), max(ys)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self._bounds()
        if bounds is None:
            painter.end()
            return
        xmin, xmax, ymin, ymax = bounds
        span_x = max(xmax - xmin, 1e-6)
        span_y = max(ymax - ymin, 1e-6)
        margin = 20
        avail_w = self.width() - 2 * margin
        avail_h = self.height() - 2 * margin
        scale = min(avail_w / span_x, avail_h / span_y) if avail_w > 0 and avail_h > 0 else 1.0

        def to_screen(point):
            x, y = point
            sx = margin + (x - xmin) * scale
            sy = self.height() - margin - (y - ymin) * scale  # flip: screen Y grows downward
            return QPointF(sx, sy)

        hidden_pen = QPen(QColor("#999999"))
        hidden_pen.setStyle(Qt.PenStyle.DashLine)
        hidden_pen.setWidthF(1.2)
        painter.setPen(hidden_pen)
        for p1, p2 in self.hidden_segments:
            painter.drawLine(to_screen(p1), to_screen(p2))

        visible_pen = QPen(QColor("#1A1A1A"))
        visible_pen.setWidthF(1.6)
        painter.setPen(visible_pen)
        for p1, p2 in self.visible_segments:
            painter.drawLine(to_screen(p1), to_screen(p2))

        painter.end()


class DetailViewDialog(QDialog):
    """Non-modal (show(), never exec()) so opening a drawing view can
    never block the app's event loop -- the same class of bug that once
    made the right-click context menu hang headless test runs."""

    def __init__(self, title, visible_segments, hidden_segments, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500, 500)
        layout = QVBoxLayout(self)
        self.view = DetailViewWidget(visible_segments, hidden_segments, self)
        layout.addWidget(self.view)
