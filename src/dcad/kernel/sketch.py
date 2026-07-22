"""Minimal sketch profiles (rectangle, circle) and the extrude/revolve
operations that turn a profile into a solid -- SpaceClaim's sketch-then-pull
workflow, without a full interactive constrained 2D sketcher."""

import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.GC import GC_MakeArcOfCircle, GC_MakeCircle
from OCP.gp import gp_Pnt, gp_Vec, gp_Circ, gp_Elips, gp_Ax2, gp_Ax1, gp_Dir
from OCP.TopoDS import TopoDS_Face, TopoDS_Shape, TopoDS_Wire


def rectangle_profile(x0: float, y0: float, x1: float, y1: float, z: float = 0.0) -> TopoDS_Face:
    if x0 == x1 or y0 == y1:
        raise ValueError("rectangle corners must differ in both x and y")
    poly = BRepBuilderAPI_MakePolygon()
    poly.Add(gp_Pnt(x0, y0, z))
    poly.Add(gp_Pnt(x1, y0, z))
    poly.Add(gp_Pnt(x1, y1, z))
    poly.Add(gp_Pnt(x0, y1, z))
    poly.Close()
    return BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()


def revolve_profile_rectangle(r0: float, z0: float, r1: float, z1: float) -> TopoDS_Face:
    """A rectangle in the XZ plane (radius vs. height), for revolving about
    the Z axis into a tube/cylinder/ring. `revolve()` on an XY-plane profile
    (e.g. from `rectangle_profile`/`circle_profile`) sweeps zero volume,
    since that plane is perpendicular to, not containing, the Z axis.
    """
    if r0 == r1 or z0 == z1:
        raise ValueError("revolve profile corners must differ in both r and z")
    if min(r0, r1) < 0:
        raise ValueError("revolve profile radius must be non-negative")
    poly = BRepBuilderAPI_MakePolygon()
    poly.Add(gp_Pnt(r0, 0, z0))
    poly.Add(gp_Pnt(r1, 0, z0))
    poly.Add(gp_Pnt(r1, 0, z1))
    poly.Add(gp_Pnt(r0, 0, z1))
    poly.Close()
    return BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()


def circle_profile(cx: float, cy: float, radius: float, z: float = 0.0) -> TopoDS_Face:
    if radius <= 0:
        raise ValueError("circle radius must be positive")
    circ = gp_Circ(gp_Ax2(gp_Pnt(cx, cy, z), gp_Dir(0, 0, 1)), radius)
    edge = BRepBuilderAPI_MakeEdge(circ).Edge()
    wire = BRepBuilderAPI_MakeWire(edge).Wire()
    return BRepBuilderAPI_MakeFace(wire, True).Face()


# -- point-driven builders for interactive (click-to-place) sketching -----
# These take raw 3D points (already projected onto whichever sketch plane
# is active) instead of assuming the XY plane, so the same interactive
# sketch session works for both an extrude plane (XY, normal +Z) and a
# revolve plane (XZ, normal +Y).

Point3 = tuple


def polygon_profile(points: list) -> TopoDS_Face:
    """A closed polygon face through 3+ coplanar points, in order."""
    if len(points) < 3:
        raise ValueError("a polygon needs at least 3 points")
    poly = BRepBuilderAPI_MakePolygon()
    for x, y, z in points:
        poly.Add(gp_Pnt(x, y, z))
    poly.Close()
    return BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()


def rectangle_points_from_corners(p0, p1, tol: float = 1e-6) -> list:
    """Given two opposite corners of an axis-aligned rectangle lying on a
    plane where exactly one coordinate is constant between them, return all
    four corners in order. Works for any axis-aligned sketch plane (XY, XZ,
    YZ) without needing to know which one in advance.
    """
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    if abs(z0 - z1) <= tol:
        return [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
    if abs(y0 - y1) <= tol:
        return [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]
    if abs(x0 - x1) <= tol:
        return [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)]
    raise ValueError("rectangle corners must lie on a common axis-aligned plane")


def circle_profile_3d(center, normal, radius: float) -> TopoDS_Face:
    """A circle profile at an arbitrary 3D center/normal (not just the XY
    plane, unlike `circle_profile`)."""
    if radius <= 0:
        raise ValueError("circle radius must be positive")
    circ = gp_Circ(gp_Ax2(gp_Pnt(*center), gp_Dir(*normal)), radius)
    edge = BRepBuilderAPI_MakeEdge(circ).Edge()
    wire = BRepBuilderAPI_MakeWire(edge).Wire()
    return BRepBuilderAPI_MakeFace(wire, True).Face()


def distance(p0, p1) -> float:
    return math.dist(p0, p1)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _normalize(v):
    length = math.sqrt(sum(c * c for c in v))
    if length < 1e-12:
        raise ValueError("degenerate direction (points too close together)")
    return (v[0] / length, v[1] / length, v[2] / length)


def regular_polygon_profile(center, vertex, normal, num_sides: int = 6) -> TopoDS_Face:
    """A regular N-gon, matching SpaceClaim's Polygon sketch tool: center
    click + a click for the first vertex (fixing the circumradius and
    starting angle) + a side count."""
    if num_sides < 3:
        raise ValueError("a polygon needs at least 3 sides")
    radius = distance(center, vertex)
    if radius <= 0:
        raise ValueError("polygon radius must be positive")
    u = _normalize(_sub(vertex, center))
    v = _normalize(_cross(normal, u))
    points = []
    for i in range(num_sides):
        theta = 2 * math.pi * i / num_sides
        c = math.cos(theta)
        s = math.sin(theta)
        points.append((
            center[0] + radius * (c * u[0] + s * v[0]),
            center[1] + radius * (c * u[1] + s * v[1]),
            center[2] + radius * (c * u[2] + s * v[2]),
        ))
    return polygon_profile(points)


def ellipse_profile_3d(center, major_axis_point, minor_radius: float, normal) -> TopoDS_Face:
    """SpaceClaim's Ellipse tool: center click, major-axis-endpoint click,
    then a minor radius."""
    major_radius = distance(center, major_axis_point)
    if major_radius <= 0 or minor_radius <= 0:
        raise ValueError("ellipse radii must be positive")
    if minor_radius > major_radius:
        major_radius, minor_radius = minor_radius, major_radius
    x_dir = _normalize(_sub(major_axis_point, center))
    axis = gp_Ax2(gp_Pnt(*center), gp_Dir(*normal), gp_Dir(*x_dir))
    elips = gp_Elips(axis, major_radius, minor_radius)
    edge = BRepBuilderAPI_MakeEdge(elips).Edge()
    wire = BRepBuilderAPI_MakeWire(edge).Wire()
    return BRepBuilderAPI_MakeFace(wire, True).Face()


def three_point_circle_profile(p1, p2, p3) -> TopoDS_Face:
    """SpaceClaim's Three-Point Circle tool: a circle through 3 points."""
    circ = GC_MakeCircle(gp_Pnt(*p1), gp_Pnt(*p2), gp_Pnt(*p3)).Value()
    edge = BRepBuilderAPI_MakeEdge(circ).Edge()
    wire = BRepBuilderAPI_MakeWire(edge).Wire()
    return BRepBuilderAPI_MakeFace(wire, True).Face()


def three_point_arc_segment_profile(p1, p2, p3) -> TopoDS_Face:
    """SpaceClaim's Three-Point Arc tool draws one arc edge (start p1,
    through p2, end p3) as part of a larger multi-segment sketch. This
    tool's click-and-close-immediately model doesn't support multi-segment
    profiles yet, so the arc is closed with a straight chord back to its
    start, producing the circular-segment ("D-shaped") region instead --
    a deliberate simplification, not what a bare 3-point arc alone is in
    real SpaceClaim.
    """
    arc = GC_MakeArcOfCircle(gp_Pnt(*p1), gp_Pnt(*p2), gp_Pnt(*p3)).Value()
    arc_edge = BRepBuilderAPI_MakeEdge(arc).Edge()
    chord_edge = BRepBuilderAPI_MakeEdge(gp_Pnt(*p3), gp_Pnt(*p1)).Edge()
    wire_builder = BRepBuilderAPI_MakeWire()
    wire_builder.Add(arc_edge)
    wire_builder.Add(chord_edge)
    return BRepBuilderAPI_MakeFace(wire_builder.Wire(), True).Face()


def open_polyline_wire(points: list) -> TopoDS_Wire:
    """An unclosed polyline through 2+ points -- used for the live preview
    of an in-progress Line/polygon sketch entity before it's closed."""
    if len(points) < 2:
        raise ValueError("a polyline needs at least 2 points")
    poly = BRepBuilderAPI_MakePolygon()
    for x, y, z in points:
        poly.Add(gp_Pnt(x, y, z))
    return poly.Wire()


def extrude(profile: TopoDS_Face, height: float) -> TopoDS_Shape:
    if height == 0:
        raise ValueError("extrude height must be non-zero")
    return BRepPrimAPI_MakePrism(profile, gp_Vec(0, 0, height)).Shape()


def revolve(profile: TopoDS_Face, angle_deg: float = 360.0) -> TopoDS_Shape:
    """Revolve a profile about the Z axis through the origin."""
    if not (0 < angle_deg <= 360):
        raise ValueError("revolve angle must be in (0, 360]")
    axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    if angle_deg >= 360:
        return BRepPrimAPI_MakeRevol(profile, axis, True).Shape()
    return BRepPrimAPI_MakeRevol(profile, axis, math.radians(angle_deg), True).Shape()
