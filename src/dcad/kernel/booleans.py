"""Boolean solid operations backed by OCCT's BRepAlgoAPI."""

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
from OCP.TopoDS import TopoDS_Shape


def _run(op) -> TopoDS_Shape:
    op.Build()
    if not op.IsDone():
        raise RuntimeError("boolean operation failed")
    return op.Shape()


def union(a: TopoDS_Shape, b: TopoDS_Shape) -> TopoDS_Shape:
    return _run(BRepAlgoAPI_Fuse(a, b))


def subtract(a: TopoDS_Shape, b: TopoDS_Shape) -> TopoDS_Shape:
    return _run(BRepAlgoAPI_Cut(a, b))


def intersect(a: TopoDS_Shape, b: TopoDS_Shape) -> TopoDS_Shape:
    return _run(BRepAlgoAPI_Common(a, b))
