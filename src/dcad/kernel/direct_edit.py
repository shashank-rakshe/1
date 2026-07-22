"""Direct-modeling face editing: SpaceClaim-style pull/push on a planar face.

The picked face is extruded into a prism tool along its own outward normal;
pulling outward fuses that tool onto the solid, pushing inward cuts it away.
This covers the common planar-face case, not arbitrary/curved-face pulls.
"""

from OCP.BRep import BRep_Tool
from OCP.BRepTools import BRepTools
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopoDS import TopoDS_Face, TopoDS_Shape
from OCP.gp import gp_Dir, gp_Vec

from dcad.kernel.booleans import union, subtract


def face_outward_normal(face: TopoDS_Face) -> gp_Dir:
    surface = BRep_Tool.Surface_s(face)
    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
    props = GeomLProp_SLProps(surface, (umin + umax) / 2, (vmin + vmax) / 2, 1, 1e-6)
    if not props.IsNormalDefined():
        raise RuntimeError("face normal is not defined at its center")
    normal = props.Normal()
    if face.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    return normal


def pull_face(solid: TopoDS_Shape, face: TopoDS_Face, distance: float) -> TopoDS_Shape:
    """Offset a planar face along its outward normal by `distance`.

    Positive distance pulls material outward (fuse); negative pushes
    material inward (cut).
    """
    if distance == 0:
        return solid
    normal = face_outward_normal(face)
    vec = gp_Vec(normal.X() * distance, normal.Y() * distance, normal.Z() * distance)
    tool = BRepPrimAPI_MakePrism(face, vec).Shape()
    if distance > 0:
        return union(solid, tool)
    return subtract(solid, tool)
