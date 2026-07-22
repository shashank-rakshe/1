"""Geometry repair tools matching SpaceClaim's Repair tab: Stitch
(Solidify group), Merge Faces (Adjust group), Fill (Fix group)."""

from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape


def stitch(shapes: list, tolerance: float = 1e-6) -> TopoDS_Shape:
    """Sews disjoint faces/shells that share edges (within tolerance) into
    a single connected shell, closing it into a solid if the result is
    watertight. SpaceClaim's Stitch, for healing geometry imported as
    disconnected surface patches."""
    sewing = BRepBuilderAPI_Sewing(tolerance)
    for shape in shapes:
        sewing.Add(shape)
    sewing.Perform()
    result = sewing.SewedShape()

    explorer = TopExp_Explorer(result, TopAbs_SHELL)
    if explorer.More():
        shell = TopoDS.Shell_s(explorer.Current())
        if shell.Closed():
            solid_maker = BRepBuilderAPI_MakeSolid(shell)
            if solid_maker.IsDone():
                return solid_maker.Solid()
    return result


def merge_faces(shape: TopoDS_Shape) -> TopoDS_Shape:
    """Unifies neighboring faces that lie on the same underlying surface
    (and the redundant edges between them) into single faces -- SpaceClaim's
    Merge Faces / Extra Edges, for simplifying geometry before export."""
    unifier = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    unifier.Build()
    return unifier.Shape()


def fill_faces(shape: TopoDS_Shape, faces_to_remove: list) -> TopoDS_Shape:
    """Removes the given faces and heals the resulting gap by extending
    the surrounding geometry -- SpaceClaim's Fill, for removing rounds,
    chamfers, protrusions, or depressions."""
    defeaturing = BRepAlgoAPI_Defeaturing()
    defeaturing.SetShape(shape)
    for face in faces_to_remove:
        defeaturing.AddFaceToRemove(face)
    defeaturing.Build()
    if not defeaturing.IsDone():
        raise RuntimeError("fill failed -- the selected face(s) may not be removable")
    return defeaturing.Shape()
