"""Solid primitive constructors backed by OCCT's BRepPrimAPI."""

from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
)
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.TopoDS import TopoDS_Shape


def make_box(dx: float, dy: float, dz: float, origin: gp_Pnt | None = None) -> TopoDS_Shape:
    if dx <= 0 or dy <= 0 or dz <= 0:
        raise ValueError("box dimensions must be positive")
    origin = origin or gp_Pnt(0, 0, 0)
    return BRepPrimAPI_MakeBox(origin, dx, dy, dz).Shape()


def make_cylinder(radius: float, height: float, origin: gp_Pnt | None = None) -> TopoDS_Shape:
    if radius <= 0 or height <= 0:
        raise ValueError("cylinder radius/height must be positive")
    axis = gp_Ax2(origin or gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(axis, radius, height).Shape()


def make_sphere(radius: float, origin: gp_Pnt | None = None) -> TopoDS_Shape:
    if radius <= 0:
        raise ValueError("sphere radius must be positive")
    return BRepPrimAPI_MakeSphere(origin or gp_Pnt(0, 0, 0), radius).Shape()
