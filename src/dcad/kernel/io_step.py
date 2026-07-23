"""STEP / IGES import and export."""

from pathlib import Path

from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.IGESControl import IGESControl_Reader, IGESControl_Writer
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopoDS import TopoDS_Shape
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name


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


def _label_name(label: TDF_Label) -> str:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return ""


def import_step_assembly(path: str) -> list[tuple[str, TopoDS_Shape, tuple[str, ...]]]:
    """Import a STEP file preserving each part's name and assembly-group
    path (e.g. ("Gearbox", "Housing")), via OCCT's XDE/XCAF layer instead
    of the plain STEPControl_Reader `import_step_multi()` uses -- XDE is
    what actually carries STEP AP214 part names and assembly component
    structure; the plain reader only ever returns anonymous root shapes,
    which is why imported assemblies previously showed up as a flat list
    of "Solid1", "Solid2", ... with no structure matching the original
    file.

    Returns a flat list of (name, located_shape, group_path) for every
    leaf part -- group_path is the tuple of ancestor assembly names,
    empty for a standalone part -- so the caller can add each part as its
    own selectable document object while still rebuilding the assembly
    nesting for display (e.g. the structure tree). Falls back to
    `import_step_multi()` (unnamed, ungrouped parts) if the file carries
    no XDE name/structure data at all.
    """
    if not Path(path).exists():
        raise FileNotFoundError(path)

    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.InitDocument(doc)

    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed (status={status})")
    if not reader.Transfer(doc):
        raise RuntimeError("STEP/XDE transfer failed")

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    results: list[tuple[str, TopoDS_Shape, tuple[str, ...]]] = []

    def walk(label: TDF_Label, group_path: tuple[str, ...]) -> None:
        real_label = label
        if shape_tool.IsReference_s(label):
            referred = TDF_Label()
            shape_tool.GetReferredShape_s(label, referred)
            real_label = referred
        name = _label_name(label)
        if not name or (name.startswith("=>[") and name.endswith("]")):
            # A component reference with no instance-specific name of its
            # own gets an auto-generated placeholder name from OCCT of the
            # form "=>[0:1:1:1]" (the referred label's own Entry() path) --
            # not useful to show, so fall back to the master part's name.
            name = _label_name(real_label)
        if shape_tool.IsAssembly_s(real_label):
            children = TDF_LabelSequence()
            shape_tool.GetComponents_s(real_label, children)
            child_path = group_path + (name or "Assembly",)
            for i in range(1, children.Length() + 1):
                walk(children.Value(i), child_path)
        else:
            shape = shape_tool.GetShape_s(label)
            if not shape.IsNull():
                results.append((name, shape, group_path))

    free_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_labels)
    for i in range(1, free_labels.Length() + 1):
        walk(free_labels.Value(i), ())

    if not results:
        return [("", shape, ()) for shape in import_step_multi(path)]
    return results


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
