"""Handle multipart uploads to ComfyUI/input/tmp/."""
import os
import uuid
import folder_paths

from .utils import view_url, guess_ext


async def save_uploaded_files(request, base_url: str):
    reader = await request.multipart()
    input_dir = folder_paths.get_input_directory()
    tmp_dir = os.path.join(input_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    saved = []
    async for field in reader:
        if field is None:
            break
        if field.name not in ("file", "files", "image"):
            continue
        orig = field.filename or "upload"
        ext = guess_ext(orig, field.headers.get("Content-Type", ""))
        name = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(tmp_dir, name)
        with open(path, "wb") as f:
            while True:
                chunk = await field.read_chunk(1 << 15)
                if not chunk:
                    break
                f.write(chunk)
        rel = f"tmp/{name}"
        saved.append({
            "name": rel,
            "original_name": orig,
            "url": view_url(base_url, name, "tmp", "input"),
        })
    return saved
