"""XML loader that converts structural models into Structure.from_dict()-compatible dictionaries."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


def load_structure_from_xml(xml_path: str | Path) -> dict:
    """
    Read a structural model XML and return a dictionary compatible with Structure.from_dict().

    Output schema:
      - nodes: [{id, x, y, restraints}]
      - materials: [{id, E, alpha?}]
      - sections: [{id, A, I, d?}]
      - elements: [{id, type, node_i, node_j, material, section, member_loads}]
      - nodal_loads: [{node, fx, fy, mz}]
    """
    root = ET.parse(str(xml_path)).getroot()

    model = {
        "nodes": _parse_nodes(root),
        "materials": _parse_materials(root),
        "sections": _parse_sections(root),
        "elements": _parse_elements(root),
        "nodal_loads": _parse_nodal_loads(root),
    }
    return model


def _parse_nodes(root: ET.Element) -> list[dict]:
    nodes = []
    for node in root.findall("./nodes/node"):
        restraints_elem = node.find("restraints")
        restraints = _parse_bool_triplet(restraints_elem, ("ux", "uy", "rz"))

        nodes.append(
            {
                "id": _to_int(_pick(node, "id", required=True)),
                "x": _to_float(_pick(node, "x", required=True)),
                "y": _to_float(_pick(node, "y", required=True)),
                "restraints": restraints,
            }
        )
    return nodes


def _parse_materials(root: ET.Element) -> list[dict]:
    materials = []
    for mat in root.findall("./materials/material"):
        data = {
            "id": _pick(mat, "id", required=True),
            "E": _to_float(_pick(mat, "E", "e", required=True)),
        }

        alpha_raw = _pick(mat, "alpha")
        if alpha_raw is not None:
            data["alpha"] = _to_float(alpha_raw)

        materials.append(data)
    return materials


def _parse_sections(root: ET.Element) -> list[dict]:
    sections = []
    for sec in root.findall("./sections/section"):
        data = {
            "id": _pick(sec, "id", required=True),
            "A": _to_float(_pick(sec, "A", "a", required=True)),
            "I": _to_float(_pick(sec, "I", "i", required=True)),
        }

        # Accept either d or depth in XML and normalize to solver key d.
        depth_raw = _pick(sec, "d", "depth")
        if depth_raw is not None:
            data["d"] = _to_float(depth_raw)

        sections.append(data)
    return sections


def _parse_elements(root: ET.Element) -> list[dict]:
    elements = []
    for elem in root.findall("./elements/element"):
        data = {
            "id": _to_int(_pick(elem, "id", required=True)),
            "type": _pick(elem, "type", required=True),
            "node_i": _to_int(_pick(elem, "node_i", "nodeI", "ni", required=True)),
            "node_j": _to_int(_pick(elem, "node_j", "nodeJ", "nj", required=True)),
            "material": _pick(elem, "material", required=True),
            "section": _pick(elem, "section", required=True),
        }

        releases_elem = elem.find("releases")
        if releases_elem is not None:
            releases = {}
            for key in ("start", "end"):
                raw = _pick(releases_elem, key)
                if raw is not None:
                    releases[key] = _to_bool(raw)
            if releases:
                data["releases"] = releases

        member_loads = _parse_member_loads(elem)
        if member_loads:
            data["member_loads"] = member_loads

        elements.append(data)
    return elements


def _parse_member_loads(elem: ET.Element) -> list[dict]:
    loads = []

    container = elem.find("member_loads")
    if container is None:
        container = elem.find("memberLoads")

    if container is None:
        return loads

    for load in container:
        if load.tag not in {"load", "member_load", "memberLoad"}:
            continue

        payload: dict = {}

        # Attributes first
        for key, value in load.attrib.items():
            payload[key] = _coerce(value)

        # Then child tags; they override attributes if duplicated.
        for child in list(load):
            if child.text is not None:
                payload[child.tag] = _coerce(child.text)

        # Normalize common aliases.
        if "p" not in payload and "P" in payload:
            payload["p"] = payload["P"]
        if "a" not in payload and "x" in payload:
            payload["a"] = payload["x"]
        if "w" not in payload and "W" in payload:
            payload["w"] = payload["W"]

        if "type" in payload:
            payload["type"] = str(payload["type"])

        loads.append(payload)

    return loads


def _parse_nodal_loads(root: ET.Element) -> list[dict]:
    loads = []

    for ld in root.findall("./nodal_loads/load") + root.findall("./nodalLoads/load"):
        data = {
            "node": _to_int(_pick(ld, "node", required=True)),
            "fx": _to_float(_pick(ld, "fx", "Fx", default="0.0")),
            "fy": _to_float(_pick(ld, "fy", "Fy", default="0.0")),
            "mz": _to_float(_pick(ld, "mz", "Mz", default="0.0")),
        }
        loads.append(data)

    return loads


def _parse_bool_triplet(elem: ET.Element | None, keys: tuple[str, ...]) -> dict:
    if elem is None:
        return {k: False for k in keys}

    out = {}
    for key in keys:
        raw = _pick(elem, key)
        out[key] = _to_bool(raw) if raw is not None else False
    return out


def _pick(elem: ET.Element, *keys: str, required: bool = False, default: str | None = None) -> str | None:
    for key in keys:
        if key in elem.attrib:
            value = elem.attrib[key]
            if value is not None:
                return value.strip()

        child = elem.find(key)
        if child is not None and child.text is not None:
            return child.text.strip()

    if required:
        raise ValueError(f"Missing required XML field {keys} in <{elem.tag}>.")
    return default


def _coerce(value: str) -> bool | float | str:
    text = value.strip()
    lower = text.lower()

    if lower == "true":
        return True
    if lower == "false":
        return False

    try:
        return float(text)
    except ValueError:
        return text


def _to_bool(value: str) -> bool:
    lower = value.strip().lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    raise ValueError(f"Expected boolean string 'true'/'false', got {value!r}.")


def _to_float(value: str) -> float:
    return float(value)


def _to_int(value: str) -> int:
    return int(float(value))
