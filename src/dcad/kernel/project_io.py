"""Native project file (.dcadproj): a zip of per-object BREP files plus a
JSON manifest carrying names/ids. Not a SpaceClaim .scdoc file -- there is
no open reader for that proprietary format -- but a real, working save/load
for this tool's own documents."""

import json
import tempfile
import zipfile
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Shape

from dcad.kernel.document import Document

MANIFEST_NAME = "manifest.json"


def save_project(document: Document, path: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manifest = []
        for obj in document.objects:
            brep_name = f"object_{obj.id}.brep"
            ok = BRepTools.Write_s(obj.shape, str(tmp_path / brep_name))
            if not ok:
                raise RuntimeError(f"failed to serialize {obj.name}")
            manifest.append({"id": obj.id, "name": obj.name, "brep": brep_name})
        (tmp_path / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2))

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_path / MANIFEST_NAME, MANIFEST_NAME)
            for entry in manifest:
                zf.write(tmp_path / entry["brep"], entry["brep"])


def load_project(path: str) -> Document:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    document = Document()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(tmp_path)
        manifest = json.loads((tmp_path / MANIFEST_NAME).read_text())
        for entry in manifest:
            shape = TopoDS_Shape()
            builder = BRep_Builder()
            ok = BRepTools.Read_s(shape, str(tmp_path / entry["brep"]), builder)
            if not ok or shape.IsNull():
                raise RuntimeError(f"failed to read {entry['name']}")
            document.add(shape, name=entry["name"])
    return document
