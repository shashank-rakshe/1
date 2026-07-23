"""Assembly-level operations: bringing one component's face into contact
with another's (SpaceClaim's Assembly > Align), and rotating a component
so a picked edge points the same way as another's (Assembly > Orient)."""

from OCP.TopoDS import TopoDS_Shape, TopoDS_Face, TopoDS_Edge
from OCP.TopAbs import TopAbs_REVERSED
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Line
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax3, gp_Trsf, gp_Pnt, gp_Dir
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform


def _face_centroid(face: TopoDS_Face) -> gp_Pnt:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return props.CentreOfMass()


def _outward_normal(face: TopoDS_Face, geometric_normal: gp_Dir) -> gp_Dir:
    """A face's Orientation() flag can flip its effective outward normal
    relative to the underlying surface's own geometric normal (e.g. a
    box's -Z bottom face has a geometric normal of +Z but is marked
    REVERSED) -- account for that so Align's contact/facing direction is
    actually outward, not just whatever the surface's math happens to give."""
    return geometric_normal.Reversed() if face.Orientation() == TopAbs_REVERSED else geometric_normal


def align_faces(
    moving_shape: TopoDS_Shape,
    moving_face: TopoDS_Face,
    stationary_face: TopoDS_Face,
) -> TopoDS_Shape:
    """Move (translate + rotate) `moving_shape` so `moving_face` becomes
    coincident with `stationary_face` -- the direct-modeling equivalent of
    SpaceClaim's Assembly > Align: select the face to move, then the face
    to remain stationary.

    Planar faces are brought flush and facing each other (their outward
    normals end up anti-parallel, like two mating surfaces in contact).
    Cylindrical faces are made concentric (their axes coincide) so a pin
    seats in a hole; no particular rotation about that shared axis is
    implied -- SpaceClaim itself treats that as a separate Orient step.
    """
    m_adaptor = BRepAdaptor_Surface(moving_face, True)
    s_adaptor = BRepAdaptor_Surface(stationary_face, True)
    m_type = m_adaptor.GetType()
    s_type = s_adaptor.GetType()
    if m_type != s_type or m_type not in (GeomAbs_Plane, GeomAbs_Cylinder):
        raise ValueError("Align requires two faces of the same kind: both planar or both cylindrical")

    if m_type == GeomAbs_Plane:
        from_point = _face_centroid(moving_face)
        from_dir = _outward_normal(moving_face, m_adaptor.Plane().Axis().Direction())
        to_point = _face_centroid(stationary_face)
        to_dir = _outward_normal(stationary_face, s_adaptor.Plane().Axis().Direction()).Reversed()
    else:
        from_point = m_adaptor.Cylinder().Location()
        from_dir = _outward_normal(moving_face, m_adaptor.Cylinder().Axis().Direction())
        to_point = s_adaptor.Cylinder().Location()
        to_dir = _outward_normal(stationary_face, s_adaptor.Cylinder().Axis().Direction())

    from_frame = gp_Ax3(from_point, from_dir)
    to_frame = gp_Ax3(to_point, to_dir)
    trsf = gp_Trsf()
    trsf.SetDisplacement(from_frame, to_frame)
    return BRepBuilderAPI_Transform(moving_shape, trsf, True).Shape()


def _edge_direction(edge: TopoDS_Edge) -> gp_Dir:
    curve = BRepAdaptor_Curve(edge)
    if curve.GetType() != GeomAbs_Line:
        raise ValueError("Orient requires straight edges")
    direction = curve.Line().Direction()
    return direction.Reversed() if edge.Orientation() == TopAbs_REVERSED else direction


def orient_edges(
    moving_shape: TopoDS_Shape,
    moving_edge: TopoDS_Edge,
    stationary_edge: TopoDS_Edge,
) -> TopoDS_Shape:
    """Rotate `moving_shape` in place -- about the midpoint of
    `moving_edge` -- so that edge points the same way as `stationary_edge`.

    This is SpaceClaim's Assembly > Orient: the follow-up to Align that
    fixes the rotation *about* an already-shared axis or plane (Align
    alone leaves that rotation at whatever the faces' default frames
    happened to produce)."""
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(moving_edge, props)
    pivot = props.CentreOfMass()

    from_dir = _edge_direction(moving_edge)
    to_dir = _edge_direction(stationary_edge)

    from_frame = gp_Ax3(pivot, from_dir)
    to_frame = gp_Ax3(pivot, to_dir)
    trsf = gp_Trsf()
    trsf.SetDisplacement(from_frame, to_frame)
    return BRepBuilderAPI_Transform(moving_shape, trsf, True).Shape()
