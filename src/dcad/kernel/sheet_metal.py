"""Sheet metal: bend-allowance math and the Flange tool (SpaceClaim's
Sheet Metal tab). Unfold/Fold/Flatten -- walking a part's face-adjacency
graph to classify and unroll every bend -- is a materially bigger, separate
algorithm and isn't built yet; see the README."""

import math

from OCP.TopoDS import TopoDS_Face, TopoDS_Edge, TopoDS_Shape, TopoDS
from OCP.TopAbs import TopAbs_REVERSED, TopAbs_FACE, TopAbs_EDGE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Line
from OCP.gp import gp_Pnt, gp_Dir, gp_Vec, gp_Ax2, gp_Ax3, gp_Trsf
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeBox
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from dcad.kernel import booleans


def bend_allowance(radius: float, angle_deg: float, thickness: float, k_factor: float = 0.33) -> float:
    """Standard sheet-metal bend-allowance formula: the arc length of the
    neutral axis through the bend, which is what a flat pattern needs to
    add for that bend. `k_factor` (0.25-0.50) locates the neutral axis
    between the inner surface (0.25) and the mid-thickness (0.50)."""
    if not (0.0 <= k_factor <= 1.0):
        raise ValueError("k_factor must be between 0 and 1")
    if radius <= 0 or thickness <= 0:
        raise ValueError("radius and thickness must be positive")
    return math.radians(angle_deg) * (radius + k_factor * thickness)


def flat_length(flat_segments: float, radius: float, angle_deg: float, thickness: float, k_factor: float = 0.33) -> float:
    """Total flat-pattern length of a part made of straight `flat_segments`
    (the sum of every flat wall's length) plus one bend of the given
    radius/angle/thickness -- the flat segments plus that bend's allowance."""
    return flat_segments + bend_allowance(radius, angle_deg, thickness, k_factor)


def _outward_normal(face: TopoDS_Face, geometric_normal: gp_Dir) -> gp_Dir:
    return geometric_normal.Reversed() if face.Orientation() == TopAbs_REVERSED else geometric_normal


def _edge_endpoints(edge: TopoDS_Edge):
    curve = BRepAdaptor_Curve(edge)
    if curve.GetType() != GeomAbs_Line:
        raise ValueError("Flange requires a straight edge")
    p1 = curve.Value(curve.FirstParameter())
    p2 = curve.Value(curve.LastParameter())
    return p1, p2


def faces_adjacent_to_edge(shape: TopoDS_Shape, edge: TopoDS_Edge) -> list[TopoDS_Face]:
    """Every face of `shape` that has `edge` on its boundary."""
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)
    index = edge_face_map.FindIndex(edge)
    if index == 0:
        return []
    return [TopoDS.Face_s(item) for item in edge_face_map.FindFromIndex(index)]


def infer_base_face(shape: TopoDS_Shape, edge: TopoDS_Edge) -> TopoDS_Face:
    """Of the faces bordering `edge`, pick the largest-area planar one --
    for a thin sheet, that's reliably the sheet's own flat face rather
    than the thin side wall also touching that edge."""
    candidates = [f for f in faces_adjacent_to_edge(shape, edge) if BRepAdaptor_Surface(f, True).GetType() == GeomAbs_Plane]
    if not candidates:
        raise ValueError("no planar face borders this edge")

    def area_of(face):
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        return props.Mass()

    return max(candidates, key=area_of)


def infer_outward_direction(face: TopoDS_Face, edge: TopoDS_Edge) -> gp_Dir:
    """The in-plane direction, perpendicular to `edge`, that points away
    from `face`'s own material -- SpaceClaim's interactive Flange tool
    gets this from which way you drag; this infers a sensible default
    from geometry alone (works for the convex/rectangular sheets this
    tool is built for: a boundary edge's outward side is away from the
    face's centroid)."""
    face_adaptor = BRepAdaptor_Surface(face, True)
    if face_adaptor.GetType() != GeomAbs_Plane:
        raise ValueError("requires a planar face")
    normal = _outward_normal(face, face_adaptor.Plane().Axis().Direction())
    p1, p2 = _edge_endpoints(edge)
    edge_dir = gp_Dir(gp_Vec(p1, p2))
    candidate = normal.Crossed(edge_dir)

    face_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, face_props)
    centroid = face_props.CentreOfMass()
    edge_mid = gp_Pnt((p1.X() + p2.X()) / 2, (p1.Y() + p2.Y()) / 2, (p1.Z() + p2.Z()) / 2)
    to_edge = gp_Vec(centroid, edge_mid)
    if candidate.X() * to_edge.X() + candidate.Y() * to_edge.Y() + candidate.Z() * to_edge.Z() < 0:
        candidate = candidate.Reversed()
    return candidate


def make_flange(
    base_face: TopoDS_Face,
    edge: TopoDS_Edge,
    outward_dir: gp_Dir,
    thickness: float,
    wall_length: float,
    angle_deg: float,
    bend_radius: float,
) -> TopoDS_Shape:
    """Build a flange: a new wall, bent up from `edge` by `angle_deg`
    through a rounded bend of `bend_radius`, `wall_length` long past the
    bend. `outward_dir` is the in-plane direction (perpendicular to the
    edge, lying in `base_face`'s plane) the flange extends away from the
    sheet -- SpaceClaim's interactive tool gets this from a drag; here
    it's an explicit parameter.

    Returns only the new bend+wall geometry (not fused with any existing
    base solid) -- union it onto the sheet body with `kernel.booleans.union`.
    """
    if thickness <= 0 or wall_length <= 0 or bend_radius <= 0:
        raise ValueError("thickness, wall_length, and bend_radius must be positive")
    if not (0 < angle_deg <= 180):
        raise ValueError("angle_deg must be between 0 and 180")

    face_adaptor = BRepAdaptor_Surface(base_face, True)
    if face_adaptor.GetType() != GeomAbs_Plane:
        raise ValueError("Flange requires a planar base face")
    normal = _outward_normal(base_face, face_adaptor.Plane().Axis().Direction())
    p1, p2 = _edge_endpoints(edge)  # raises ValueError for a non-straight edge

    # Bend axis = the edge itself, oriented so the annulus sweep
    # (XDirection=normal, angle 0..angle_deg) rotates the radial direction
    # toward outward_dir -- i.e. so YDirection (= axis x XDirection, which
    # is where OCCT's own gp_Ax2 sweep convention rotates XDirection
    # toward) works out to outward_dir. Verified empirically: this choice
    # makes the bend's radial direction sweep from `normal` (flush with
    # the flat sheet at angle 0) to `outward_dir` (at angle 90), not the
    # reverse -- gp_Ax2's YDirection sign isn't safe to derive by hand.
    axis_dir = normal.Crossed(outward_dir)

    # The cylinder sweeps `edge_length` along +axis_dir starting at its
    # location point, so that point must be the endpoint axis_dir points
    # AWAY from -- not the edge's midpoint, or the whole bend+wall ends up
    # shifted half an edge-length sideways (caught by a bounding-box check
    # against the source edge during development).
    delta = gp_Vec(p1, p2)
    edge_length = delta.Magnitude()
    start_point = p1 if delta.Dot(gp_Vec(axis_dir.X(), axis_dir.Y(), axis_dir.Z())) > 0 else p2

    axis_point = gp_Pnt(
        start_point.X() - normal.X() * (bend_radius + thickness),
        start_point.Y() - normal.Y() * (bend_radius + thickness),
        start_point.Z() - normal.Z() * (bend_radius + thickness),
    )
    ax2 = gp_Ax2(axis_point, axis_dir, normal)
    angle_rad = math.radians(angle_deg)

    outer = BRepPrimAPI_MakeCylinder(ax2, bend_radius + thickness, edge_length, angle_rad).Shape()
    inner = BRepPrimAPI_MakeCylinder(ax2, bend_radius, edge_length, angle_rad).Shape()
    bend = booleans.subtract(outer, inner)

    # Wall: a straight box continuing from the end of the bend, in the
    # tangent direction there, `wall_length` long. radial(angle) =
    # normal*cos(angle) + outward_dir*sin(angle) is the bend's radial
    # direction at the far end (matches gp_Ax2's actual sweep, confirmed
    # empirically above); tangent is its derivative w.r.t. angle.
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    tangent = gp_Vec(
        outward_dir.X() * cos_a - normal.X() * sin_a,
        outward_dir.Y() * cos_a - normal.Y() * sin_a,
        outward_dir.Z() * cos_a - normal.Z() * sin_a,
    )
    radial_end = gp_Vec(
        normal.X() * cos_a + outward_dir.X() * sin_a,
        normal.Y() * cos_a + outward_dir.Y() * sin_a,
        normal.Z() * cos_a + outward_dir.Z() * sin_a,
    )
    # Inner-radius point at the end of the bend, in the axis's own local
    # 2D frame (XDirection=normal, YDirection=axis x XDirection).
    inner_end = gp_Vec(axis_point.X(), axis_point.Y(), axis_point.Z()) + radial_end * bend_radius

    # Wall box built in a local frame (X=length, Y=width, Z=thickness),
    # then displaced so X follows the bend's exit tangent, Y follows the
    # edge, and Z follows the bend's exit radial direction.
    box_local = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), wall_length, edge_length, thickness).Shape()
    trsf = gp_Trsf()
    from_frame = gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
    to_frame = gp_Ax3(
        gp_Pnt(inner_end.X(), inner_end.Y(), inner_end.Z()),
        gp_Dir(radial_end.X(), radial_end.Y(), radial_end.Z()),
        gp_Dir(tangent.X(), tangent.Y(), tangent.Z()),
    )
    trsf.SetDisplacement(from_frame, to_frame)
    wall = BRepBuilderAPI_Transform(box_local, trsf, True).Shape()

    return booleans.union(bend, wall)
