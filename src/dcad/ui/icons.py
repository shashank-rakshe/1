"""Procedurally-drawn (QPainter) glyph icons for the ribbon. Original line
art generated in code -- not traced from or copied out of SpaceClaim's
actual icon artwork, which is ANSYS's proprietary asset."""

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF, QPainterPath

_SIZE = 28
_COLOR = QColor("#333333")
_ACCENT = QColor("#0B5FA5")


class _Canvas:
    def __init__(self):
        self.pixmap = QPixmap(_SIZE, _SIZE)
        self.pixmap.fill(Qt.GlobalColor.transparent)
        self.painter = QPainter(self.pixmap)
        self.painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(_COLOR)
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.painter.setPen(pen)

    def accent_pen(self, width=1.8):
        pen = QPen(_ACCENT)
        pen.setWidthF(width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    def finish(self) -> QIcon:
        self.painter.end()
        return QIcon(self.pixmap)


def _pt(x, y):
    return QPointF(x, y)


def _arrow_head(p: QPainter, tip: QPointF, direction_deg: float, size: float = 5.0):
    a1 = math.radians(direction_deg + 150)
    a2 = math.radians(direction_deg - 150)
    p1 = QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1))
    p2 = QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2))
    p.drawPolygon(QPolygonF([tip, p1, p2]))


def _icon_select():
    c = _Canvas()
    c.painter.setBrush(_COLOR)
    c.painter.drawPolygon(QPolygonF([_pt(7, 5), _pt(7, 21), _pt(12, 17), _pt(15, 23), _pt(17, 22), _pt(14, 16), _pt(20, 15)]))
    return c.finish()


def _icon_box():
    c = _Canvas()
    p = c.painter
    p.drawPolygon(QPolygonF([_pt(6, 10), _pt(14, 6), _pt(22, 10), _pt(14, 14)]))
    p.drawLine(_pt(6, 10), _pt(6, 19))
    p.drawLine(_pt(22, 10), _pt(22, 19))
    p.drawLine(_pt(14, 14), _pt(14, 23))
    p.drawLine(_pt(6, 19), _pt(14, 23))
    p.drawLine(_pt(22, 19), _pt(14, 23))
    return c.finish()


def _icon_cylinder():
    c = _Canvas()
    p = c.painter
    p.drawEllipse(QRectF(6, 5, 16, 7))
    p.drawLine(_pt(6, 8.5), _pt(6, 19))
    p.drawLine(_pt(22, 8.5), _pt(22, 19))
    p.drawArc(QRectF(6, 15.5, 16, 7), 180 * 16, 180 * 16)
    return c.finish()


def _icon_sphere():
    c = _Canvas()
    p = c.painter
    p.drawEllipse(QRectF(5, 5, 18, 18))
    p.drawArc(QRectF(5, 9, 18, 10), 0, 180 * 16)
    return c.finish()


def _icon_pull():
    c = _Canvas()
    p = c.painter
    p.drawRect(QRectF(7, 15, 14, 8))
    p.drawLine(_pt(14, 13), _pt(14, 3))
    _arrow_head(p, _pt(14, 2), 90)
    return c.finish()


def _icon_move():
    c = _Canvas()
    p = c.painter
    cx, cy, r = 14, 14, 10
    for deg in (0, 90, 180, 270):
        rad = math.radians(deg)
        tip = QPointF(cx + r * math.cos(rad), cy + r * math.sin(rad))
        p.drawLine(_pt(cx, cy), tip)
        _arrow_head(p, tip, deg)
    return c.finish()


def _icon_rotate():
    c = _Canvas()
    p = c.painter
    p.drawArc(QRectF(5, 5, 18, 18), 30 * 16, 270 * 16)
    tip = QPointF(14 + 9 * math.cos(math.radians(30)), 14 + 9 * math.sin(math.radians(30)))
    _arrow_head(p, tip, -60)
    return c.finish()


def _icon_copy():
    c = _Canvas()
    p = c.painter
    p.drawRect(QRectF(5, 9, 13, 13))
    p.setBrush(Qt.GlobalColor.transparent)
    p.drawRect(QRectF(10, 5, 13, 13))
    return c.finish()


def _icon_revolve():
    c = _Canvas()
    p = c.painter
    p.drawLine(_pt(14, 3), _pt(14, 25))
    p.drawArc(QRectF(6, 8, 12, 12), 20 * 16, 200 * 16)
    tip = QPointF(14 + 6 * math.cos(math.radians(220)), 14 + 6 * math.sin(math.radians(220)))
    _arrow_head(p, tip, 130)
    return c.finish()


def _icon_venn(mode: str):
    c = _Canvas()
    p = c.painter
    rect_a, rect_b = QRectF(4, 8, 14, 14), QRectF(11, 8, 14, 14)
    p.drawEllipse(rect_a)
    p.drawEllipse(rect_b)
    if mode == "intersect":
        path_a, path_b = QPainterPath(), QPainterPath()
        path_a.addEllipse(rect_a)
        path_b.addEllipse(rect_b)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_ACCENT)
        p.drawPath(path_a.intersected(path_b))
    elif mode == "subtract":
        pen = c.accent_pen(2.2)
        p.setPen(pen)
        p.drawLine(_pt(15, 11), _pt(20, 19))
    return c.finish()


def _icon_fillet():
    c = _Canvas()
    p = c.painter
    p.drawLine(_pt(6, 6), _pt(6, 16))
    p.drawLine(_pt(16, 22), _pt(22, 22))
    p.drawArc(QRectF(6, 6, 16, 16), 90 * 16, 90 * 16)
    return c.finish()


def _icon_chamfer():
    c = _Canvas()
    p = c.painter
    p.drawLine(_pt(6, 6), _pt(6, 16))
    p.drawLine(_pt(16, 22), _pt(22, 22))
    p.drawLine(_pt(6, 16), _pt(16, 22))
    return c.finish()


def _icon_undo():
    c = _Canvas()
    p = c.painter
    p.drawArc(QRectF(6, 8, 16, 14), 30 * 16, 260 * 16)
    tip = QPointF(6 + 8 * math.cos(math.radians(30 + 260)), 15 + 7 * math.sin(math.radians(30 + 260)))
    _arrow_head(p, _pt(7, 8), -20)
    return c.finish()


def _icon_redo():
    c = _Canvas()
    p = c.painter
    p.drawArc(QRectF(6, 8, 16, 14), (180 - 30) * 16, -260 * 16)
    _arrow_head(p, _pt(21, 8), -160)
    return c.finish()


def _icon_fit_all():
    c = _Canvas()
    p = c.painter
    for x1, y1, x2, y2, x3, y3 in [
        (5, 10, 5, 5, 10, 5), (18, 5, 23, 5, 23, 10),
        (5, 18, 5, 23, 10, 23), (18, 23, 23, 23, 23, 18),
    ]:
        p.drawLine(_pt(x1, y1), _pt(x2, y2))
        p.drawLine(_pt(x2, y2), _pt(x3, y3))
    return c.finish()


def _icon_file():
    c = _Canvas()
    p = c.painter
    p.drawPolygon(QPolygonF([_pt(8, 4), _pt(17, 4), _pt(21, 8), _pt(21, 24), _pt(8, 24)]))
    p.drawLine(_pt(17, 4), _pt(17, 8))
    p.drawLine(_pt(17, 8), _pt(21, 8))
    return c.finish()


def _icon_line():
    c = _Canvas()
    p = c.painter
    p.drawLine(_pt(6, 22), _pt(22, 6))
    p.setBrush(_COLOR)
    p.drawEllipse(QRectF(4, 20, 4, 4))
    p.drawEllipse(QRectF(20, 4, 4, 4))
    return c.finish()


def _icon_rect():
    c = _Canvas()
    c.painter.drawRect(QRectF(5, 8, 18, 12))
    return c.finish()


def _icon_circle():
    c = _Canvas()
    c.painter.drawEllipse(QRectF(5, 5, 18, 18))
    return c.finish()


def _icon_polygon():
    c = _Canvas()
    p = c.painter
    pts = []
    for i in range(6):
        a = math.radians(60 * i - 90)
        pts.append(_pt(14 + 10 * math.cos(a), 14 + 10 * math.sin(a)))
    p.drawPolygon(QPolygonF(pts))
    return c.finish()


def _icon_ellipse():
    c = _Canvas()
    c.painter.drawEllipse(QRectF(3, 9, 22, 10))
    return c.finish()


def _icon_circle3pt():
    c = _Canvas()
    p = c.painter
    p.drawEllipse(QRectF(5, 5, 18, 18))
    p.setBrush(_COLOR)
    for a in (90, 210, 330):
        rad = math.radians(a)
        p.drawEllipse(QRectF(14 + 9 * math.cos(rad) - 1.5, 14 + 9 * math.sin(rad) - 1.5, 3, 3))
    return c.finish()


def _icon_arc3pt():
    c = _Canvas()
    p = c.painter
    p.drawArc(QRectF(5, 2, 18, 18), 180 * 16, 180 * 16)
    p.setBrush(_COLOR)
    p.drawEllipse(QRectF(4.5, 9.5, 3, 3))
    p.drawEllipse(QRectF(19.5, 9.5, 3, 3))
    p.drawEllipse(QRectF(12.5, 18.5, 3, 3))
    return c.finish()


def _icon_check():
    c = _Canvas()
    pen = c.accent_pen(2.4)
    c.painter.setPen(pen)
    c.painter.drawPolyline(QPolygonF([_pt(5, 15), _pt(11, 21), _pt(23, 6)]))
    return c.finish()


def _icon_cancel():
    c = _Canvas()
    pen = QPen(QColor("#B02A2A"))
    pen.setWidthF(2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    c.painter.setPen(pen)
    c.painter.drawLine(_pt(6, 6), _pt(22, 22))
    c.painter.drawLine(_pt(22, 6), _pt(6, 22))
    return c.finish()


def _icon_measure():
    c = _Canvas()
    p = c.painter
    p.drawRect(QRectF(4, 11, 20, 7))
    for x in (8, 12, 16, 20):
        p.drawLine(_pt(x, 11), _pt(x, 14))
    return c.finish()


def _icon_sketch_plane(extrude: bool):
    c = _Canvas()
    p = c.painter
    p.drawPolygon(QPolygonF([_pt(5, 16), _pt(14, 11), _pt(23, 16), _pt(14, 21)]))
    if extrude:
        p.drawLine(_pt(14, 16), _pt(14, 4))
        _arrow_head(p, _pt(14, 3), 90)
    else:
        p.drawLine(_pt(14, 21), _pt(14, 27))
        p.setPen(c.accent_pen(1.8))
        p.drawArc(QRectF(6, 1, 16, 12), 20 * 16, 200 * 16)
    return c.finish()


_BUILDERS = {
    "select": _icon_select,
    "box": _icon_box,
    "cylinder": _icon_cylinder,
    "sphere": _icon_sphere,
    "pull": _icon_pull,
    "move": _icon_move,
    "rotate": _icon_rotate,
    "copy": _icon_copy,
    "revolve": _icon_revolve,
    "merge": lambda: _icon_venn("merge"),
    "subtract": lambda: _icon_venn("subtract"),
    "intersect": lambda: _icon_venn("intersect"),
    "fillet": _icon_fillet,
    "chamfer": _icon_chamfer,
    "undo": _icon_undo,
    "redo": _icon_redo,
    "fit_all": _icon_fit_all,
    "file": _icon_file,
    "line": _icon_line,
    "rect": _icon_rect,
    "circle": _icon_circle,
    "polygon": _icon_polygon,
    "ellipse": _icon_ellipse,
    "circle3pt": _icon_circle3pt,
    "arc3pt": _icon_arc3pt,
    "check": _icon_check,
    "cancel": _icon_cancel,
    "measure": _icon_measure,
    "sketch_extrude_plane": lambda: _icon_sketch_plane(True),
    "sketch_revolve_plane": lambda: _icon_sketch_plane(False),
}

_cache = {}


def get(name: str) -> QIcon:
    if name not in _cache:
        if name not in _BUILDERS:
            raise KeyError(f"no icon registered for {name!r}")
        _cache[name] = _BUILDERS[name]()
    return _cache[name]
