"""STEP / IGES import and export."""

from pathlib import Path

from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
from OCP.IGESControl import IGESControl_Reader, IGESControl_Writer
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopoDS import TopoDS_Shape
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder


def _shapes_to_compound(shapes: list[TopoDS_Shape]) -> TopoDS_Shape:
    if len(shapes) == 1:
        return shapes[0]
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def export_step(shapes: list[TopoDS_Shape], path: str) -> None:
    writer = STEPControl_Writer()
    for shape in shapes:
        status = writer.Transfer(shape, STEPControl_AsIs)
        if status != IFSelect_RetDone:
            raise RuntimeError(f"STEP transfer failed for shape (status={status})")
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed (status={status})")


def import_step_multi(path: str) -> list[TopoDS_Shape]:
    """Import a STEP file, keeping each root shape separate instead of
    flattening the whole file into one compound.

    Large assembly files hold many independently-named parts; returning
    them as a list lets the caller add each as its own document object
    (so a big structural model stays selectable/hideable part-by-part,
    the same way it opens in SpaceClaim or Mayo)."""
    if not Path(path).exists():
        raise FileNotFoundError(path)
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed (status={status})")
    reader.TransferRoots()
    shapes = [reader.Shape(i + 1) for i in range(reader.NbShapes())]
    if not shapes:
        raise RuntimeError("STEP file contained no shapes")
    return shapes


def import_step(path: str) -> TopoDS_Shape:
    return _shapes_to_compound(import_step_multi(path))


def export_iges(shapes: list[TopoDS_Shape], path: str) -> None:
    writer = IGESControl_Writer()
    for shape in shapes:
        writer.AddShape(shape)
    writer.ComputeModel()
    if not writer.Write(str(path)):
        raise RuntimeError("IGES write failed")


def import_iges(path: str) -> TopoDS_Shape:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    reader = IGESControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"IGES read failed (status={status})")
    reader.TransferRoots()
    shapes = [reader.Shape(i + 1) for i in range(reader.NbShapes())]
    if not shapes:
        raise RuntimeError("IGES file contained no shapes")
    return _shapes_to_compound(shapes)
