"""Parse $ title markers in a workflow (ComfyUI API format) and inject params.

Title syntax (on each node's _meta.title, comma-separated):
    $var                  ->  maps params['var'] to inputs['var'] on this node
    $var.field            ->  maps params['var'] to inputs['field']
    $image                ->  LoadImage-style node; params['image'] is a path under input/
                              or an http(s) URL (caller must download first).
    $output.name          ->  mark this node as an output; its products become
                              images_by_var['name'] in the response.

Unmarked nodes keep their widget defaults; request params only override
fields that are explicitly marked.
"""
import re
import copy
from typing import Tuple, Dict, Any

MARKER_RE = re.compile(r"\$(\w+)(?:\.(\w+))?")


def parse_markers(title: str):
    if not title:
        return []
    return MARKER_RE.findall(title)


def apply_params(workflow: dict, params: dict) -> Tuple[dict, Dict[str, str]]:
    """Return (new_workflow, output_id_to_var).

    workflow is deep-copied; params override only marked fields.
    Missing params are silently skipped (defaults retained).
    """
    wf = copy.deepcopy(workflow)
    output_id_to_var: Dict[str, str] = {}
    params = params or {}

    for node_id, node in wf.items():
        if not isinstance(node, dict):
            continue
        title = (node.get("_meta") or {}).get("title", "")
        markers = parse_markers(title)
        if not markers:
            continue

        inputs = node.setdefault("inputs", {})
        for var, field in markers:
            if var == "output":
                # $output.name  -> register as output variable
                output_id_to_var[str(node_id)] = field or str(node_id)
                continue

            if var not in params:
                continue  # keep default widget value
            value = params[var]

            if var == "image" and not field:
                # LoadImage convention: inputs['image'] holds the filename
                inputs["image"] = value
            else:
                inputs[field or var] = value

    return wf, output_id_to_var
