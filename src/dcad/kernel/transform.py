"""Rigid transforms and duplication for whole solids."""

import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform, BRepBuilderAPI_Copy
from OCP.gp import gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir, gp_Vec
from OCP.TopoDS import TopoDS_Shape


def translate(shape: TopoDS_Shape, dx: float, dy: float, dz: float) -> TopoDS_Shape:
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(dx, dy, dz))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def rotate(
    shape: TopoDS_Shape,
    angle_deg: float,
    axis_point: gp_Pnt | None = None,
    axis_dir: gp_Dir | None = None,
) -> TopoDS_Shape:
    trsf = gp_Trsf()
    axis = gp_Ax1(axis_point or gp_Pnt(0, 0, 0), axis_dir or gp_Dir(0, 0, 1))
    trsf.SetRotation(axis, math.radians(angle_deg))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def duplicate(shape: TopoDS_Shape) -> TopoDS_Shape:
    return BRepBuilderAPI_Copy(shape, True).Shape()
