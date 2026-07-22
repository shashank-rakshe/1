"""Minimal sketch profiles (rectangle, circle) and the extrude/revolve
operations that turn a profile into a solid -- SpaceClaim's sketch-then-pull
workflow, without a full interactive constrained 2D sketcher."""

import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.gp import gp_Pnt, gp_Vec, gp_Circ, gp_Ax2, gp_Ax1, gp_Dir
from OCP.TopoDS import TopoDS_Face, TopoDS_Shape


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
