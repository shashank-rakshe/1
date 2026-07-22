"""Simulation-prep tools matching SpaceClaim's Prepare tab: Interference,
Enclosure/Volume Extract, Share Topology."""

from OCP.BOPAlgo import BOPAlgo_Builder
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape

from dcad.kernel import primitives
from dcad.kernel.booleans import intersect, subtract
from dcad.kernel.transform import translate


def _volume_of(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def check_interference(shapes: list) -> list:
    """Returns [(i, j, overlap_volume), ...] for every pair of solids
    (by index into `shapes`) whose volumes overlap -- SpaceClaim's
    Interference tool, for assembly QA before simulation."""
    hits = []
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            try:
                overlap = intersect(shapes[i], shapes[j])
            except Exception:
                continue
            volume = _volume_of(overlap)
            if volume > 1e-9:
                hits.append((i, j, volume))
    return hits


def bounding_box(shape: TopoDS_Shape) -> tuple:
    """(xmin, ymin, zmin, xmax, ymax, zmax)."""
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return box.Get()


def make_enclosure(shapes: list, margin: float) -> TopoDS_Shape:
    """A box surrounding all `shapes` (expanded by `margin` on every side)
    with the shapes themselves subtracted out -- the surrounding "void"
    volume, e.g. a CFD fluid domain around a solid part. SpaceClaim's
    Enclosure / Volume Extract."""
    if not shapes:
        raise ValueError("need at least one shape to build an enclosure around")
    if margin <= 0:
        raise ValueError("enclosure margin must be positive")

    xmin = ymin = zmin = float("inf")
    xmax = ymax = zmax = float("-inf")
    for shape in shapes:
        x0, y0, z0, x1, y1, z1 = bounding_box(shape)
        xmin, ymin, zmin = min(xmin, x0), min(ymin, y0), min(zmin, z0)
        xmax, ymax, zmax = max(xmax, x1), max(ymax, y1), max(zmax, z1)

    enclosure = primitives.make_box(
        xmax - xmin + 2 * margin, ymax - ymin + 2 * margin, zmax - zmin + 2 * margin,
    )
    enclosure = translate(enclosure, xmin - margin, ymin - margin, zmin - margin)
    for shape in shapes:
        enclosure = subtract(enclosure, shape)
    return enclosure


def share_topology(shapes: list) -> TopoDS_Shape:
    """Fuses touching/intersecting bodies' topology (matching face/edge/
    vertex connections at their contact interfaces) while keeping them as
    separate solids in the result -- unlike Combine/Merge, which would
    weld them into one solid. SpaceClaim's Share Topology, so a downstream
    mesher gets conformal nodes across contacting boundaries."""
    if len(shapes) < 2:
        raise ValueError("share topology needs at least two shapes")
    builder = BOPAlgo_Builder()
    for shape in shapes:
        builder.AddArgument(shape)
    builder.Perform()
    if builder.HasErrors():
        raise RuntimeError("share topology failed")
    return builder.Shape()


def explode_solids(shape: TopoDS_Shape) -> list:
    """Every top-level TopAbs_SOLID inside `shape` (e.g. a Share Topology
    result compound), for splitting it back into separate document objects
    that keep their individual identity."""
    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solids.append(TopoDS.Solid_s(explorer.Current()))
        explorer.Next()
    return solids
