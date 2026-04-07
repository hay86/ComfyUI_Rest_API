"""Resolve `workflow` field from a request: dict | URL | saved name.

Saved workflows live in:  {user_dir}/default/api_workflows/<name>.json
"""
import json
import os
import aiohttp

import folder_paths


def api_workflows_dir() -> str:
    path = os.path.join(folder_paths.get_user_directory(), "default", "api_workflows")
    os.makedirs(path, exist_ok=True)
    return path


def list_workflows():
    d = api_workflows_dir()
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(d)
        if f.endswith(".json") and os.path.isfile(os.path.join(d, f))
    )


def load_by_name(name: str) -> dict:
    # forbid path traversal
    safe = os.path.basename(name)
    if safe != name or not safe:
        raise ValueError(f"invalid workflow name: {name!r}")
    path = os.path.join(api_workflows_dir(), f"{safe}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"workflow not found: {safe}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_by_name(name: str, workflow: dict) -> str:
    safe = os.path.basename(name)
    if safe != name or not safe:
        raise ValueError(f"invalid workflow name: {name!r}")
    path = os.path.join(api_workflows_dir(), f"{safe}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    return path


async def fetch_url(url: str) -> dict:
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url) as resp:
            resp.raise_for_status()
            text = await resp.text()
            return json.loads(text)


async def resolve_workflow(value) -> dict:
    """Accepts dict, http(s):// URL, or saved workflow name."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return await fetch_url(value)
        return load_by_name(value)
    raise ValueError("workflow must be a dict, URL string, or saved name")
