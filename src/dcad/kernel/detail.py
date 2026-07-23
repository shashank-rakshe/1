"""2D drawing views: hidden-line-removed projections of the 3D model onto
a viewing plane (SpaceClaim's Detail tab -- Front/Top/Right/Isometric
views placed on a drawing sheet)."""

from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.TopoDS import TopoDS_Shape, TopoDS
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.BRepAdaptor import BRepAdaptor_Curve

# Each standard view is (look direction, in-plane "horizontal" reference
# direction) -- together they fix how the 3D model's axes map onto the
# drawing sheet's 2D X/Y.
VIEWS = {
    "front": (gp_Dir(0, -1, 0), gp_Dir(1, 0, 0)),
    "top": (gp_Dir(0, 0, -1), gp_Dir(1, 0, 0)),
    "right": (gp_Dir(-1, 0, 0), gp_Dir(0, 1, 0)),
    "isometric": (gp_Dir(-1, -1, -1), gp_Dir(1, -1, 0)),
}


def _edges_of(shape: TopoDS_Shape):
    edges = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edges.append(TopoDS.Edge_s(explorer.Current()))
        explorer.Next()
    return edges


def _segment(edge) -> tuple:
    """An HLR output edge is flattened into the projection plane (its
    world Z is ~0 in that plane's local frame), so its world X/Y are
    directly the drawing sheet's 2D coordinates."""
    curve = BRepAdaptor_Curve(edge)
    p1 = curve.Value(curve.FirstParameter())
    p2 = curve.Value(curve.LastParameter())
    return (p1.X(), p1.Y()), (p2.X(), p2.Y())


def project_view(shapes: list[TopoDS_Shape], view: str) -> tuple[list, list]:
    """Compute a hidden-line-removed 2D projection of `shapes` for one of
    the standard views (see VIEWS). Returns (visible_segments,
    hidden_segments); each segment is ((x1, y1), (x2, y2)) in the drawing
    sheet's local 2D coordinates."""
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}; choose one of {sorted(VIEWS)}")
    if not shapes:
        raise ValueError("need at least one shape to project")

    direction, x_dir = VIEWS[view]
    algo = HLRBRep_Algo()
    for shape in shapes:
        algo.Add(shape)
    axis = gp_Ax2(gp_Pnt(0, 0, 0), direction, x_dir)
    algo.Projector(HLRAlgo_Projector(axis))
    algo.Update()
    algo.Hide()

    to_shape = HLRBRep_HLRToShape(algo)
    # VCompound/HCompound: sharp edges (face-to-face angle discontinuities).
    # OutLineV/HCompound: silhouette outlines on curved surfaces (a
    # cylinder's side view has no sharp edge along its rounded side, only
    # a silhouette) -- combining both catches primitives and fillets alike.
    visible = [_segment(e) for e in _edges_of(to_shape.VCompound())]
    visible += [_segment(e) for e in _edges_of(to_shape.OutLineVCompound())]
    hidden = [_segment(e) for e in _edges_of(to_shape.HCompound())]
    hidden += [_segment(e) for e in _edges_of(to_shape.OutLineHCompound())]
    return visible, hidden
