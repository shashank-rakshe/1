"""Edge fillet and chamfer operations."""

from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
from OCP.TopoDS import TopoDS_Edge, TopoDS_Shape


def fillet_edge(solid: TopoDS_Shape, edge: TopoDS_Edge, radius: float) -> TopoDS_Shape:
    if radius <= 0:
        raise ValueError("fillet radius must be positive")
    mk = BRepFilletAPI_MakeFillet(solid)
    mk.Add(radius, edge)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("fillet failed")
    return mk.Shape()


def chamfer_edge(solid: TopoDS_Shape, edge: TopoDS_Edge, distance: float) -> TopoDS_Shape:
    if distance <= 0:
        raise ValueError("chamfer distance must be positive")
    mk = BRepFilletAPI_MakeChamfer(solid)
    mk.Add(distance, edge)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("chamfer failed")
    return mk.Shape()
