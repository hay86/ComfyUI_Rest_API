"""Helpers: base URL, URL downloads, output -> URL mapping."""
import os
import uuid
import mimetypes
import urllib.parse
import aiohttp

import folder_paths


def build_base_url(request) -> str:
    """Derive public base URL from request headers, with sensible fallbacks."""
    headers = request.headers
    proto = headers.get("X-Forwarded-Proto") or headers.get("X-Scheme") or request.url.scheme or "http"
    host = headers.get("X-Forwarded-Host") or headers.get("Host") or request.host
    return f"{proto}://{host}"


def view_url(base_url: str, filename: str, subfolder: str = "", type_: str = "output") -> str:
    q = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": type_})
    return f"{base_url}/view?{q}"


_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}


async def download_to_input_tmp(url: str) -> str:
    """Download a remote URL into ComfyUI/input/tmp/ and return relative name 'tmp/<file>'."""
    input_dir = folder_paths.get_input_directory()
    tmp_dir = os.path.join(input_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    async with aiohttp.ClientSession() as sess:
        async with sess.get(url) as resp:
            resp.raise_for_status()
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            ext = _EXT_BY_MIME.get(ctype) or os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".bin"
            name = f"{uuid.uuid4().hex}{ext}"
            path = os.path.join(tmp_dir, name)
            with open(path, "wb") as f:
                while True:
                    chunk = await resp.content.read(1 << 15)
                    if not chunk:
                        break
                    f.write(chunk)
    return f"tmp/{name}"


def guess_ext(filename: str, content_type: str = "") -> str:
    ext = os.path.splitext(filename)[1]
    if ext:
        return ext
    return _EXT_BY_MIME.get(content_type.split(";")[0].strip(), "") or mimetypes.guess_extension(content_type or "") or ""


def extract_outputs(history_entry: dict, base_url: str, output_id_to_var: dict) -> dict:
    """Convert a history entry's outputs into URL lists + variable mapping.

    Returns: {images:[], images_by_var:{}, texts_by_var:{}}
    """
    images = []
    images_by_var = {}
    texts_by_var = {}

    outputs = (history_entry or {}).get("outputs", {}) or {}
    for node_id, node_out in outputs.items():
        var = output_id_to_var.get(str(node_id), str(node_id))
        urls_for_node = []

        for key in ("images", "gifs", "audio", "videos"):
            items = node_out.get(key) or []
            for it in items:
                fn = it.get("filename")
                if not fn:
                    continue
                url = view_url(base_url, fn, it.get("subfolder", ""), it.get("type", "output"))
                urls_for_node.append(url)

        if urls_for_node:
            images.extend(urls_for_node)
            images_by_var.setdefault(var, []).extend(urls_for_node)

        # Text outputs (ShowText, etc.)
        for key in ("text", "string", "texts"):
            val = node_out.get(key)
            if val is None:
                continue
            if isinstance(val, list):
                texts_by_var.setdefault(var, []).extend([str(v) for v in val])
            else:
                texts_by_var.setdefault(var, []).append(str(val))

    return {"images": images, "images_by_var": images_by_var, "texts_by_var": texts_by_var}
