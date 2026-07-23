"""Measurement: distance between any two (sub-)shapes, and the intrinsic
size of a single one (edge length, face area, solid volume)."""

from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID
from OCP.TopoDS import TopoDS_Shape


def distance_between(shape_a: TopoDS_Shape, shape_b: TopoDS_Shape) -> float:
    calc = BRepExtrema_DistShapeShape(shape_a, shape_b)
    if not calc.IsDone():
        raise RuntimeError("distance computation failed")
    return calc.Value()


def length_of_edge(edge) -> float:
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, props)
    return props.Mass()


def area_of_face(face) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.Mass()


def volume_of_solid(solid) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    return props.Mass()


def describe(shape: TopoDS_Shape) -> str:
    """A human-readable measurement for a single picked (sub-)shape."""
    shape_type = shape.ShapeType()
    if shape_type == TopAbs_EDGE:
        return f"Length: {length_of_edge(shape):.4g}"
    if shape_type == TopAbs_FACE:
        return f"Area: {area_of_face(shape):.4g}"
    if shape_type == TopAbs_SOLID:
        return f"Volume: {volume_of_solid(shape):.4g}"
    return "No measurement available for this selection"
