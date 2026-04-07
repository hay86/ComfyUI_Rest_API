"""HTTP routes under /rest/v1/."""
import asyncio
import logging
import uuid

from aiohttp import web

from . import task_store
from .executor import submit_prompt, wait_for_history
from .uploader import save_uploaded_files
from .utils import build_base_url, extract_outputs, download_to_input_tmp
from .workflow_format import apply_params
from .workflow_loader import (
    api_workflows_dir,
    list_workflows,
    load_by_name,
    resolve_workflow,
    save_by_name,
)

log = logging.getLogger("rest_api")

PREFIX = "/rest/v1"


async def _prepare_prompt(workflow_value, params: dict):
    """Resolve workflow, download any URL-style $image params, apply markers."""
    wf = await resolve_workflow(workflow_value)
    params = dict(params or {})

    # If $image param is a remote URL, download to input/tmp/ first.
    for k, v in list(params.items()):
        if isinstance(v, str) and (v.startswith("http://") or v.startswith("https://")):
            # Heuristic: only auto-download for image-like keys; others stay as-is.
            if k in ("image", "video", "audio", "mask") or k.endswith("_image"):
                params[k] = await download_to_input_tmp(v)

    prompt, output_id_to_var = apply_params(wf, params)
    return prompt, output_id_to_var


async def _run_and_collect(prompt, output_id_to_var, base_url, timeout):
    prompt_id, node_errors = await submit_prompt(prompt)
    entry = await wait_for_history(prompt_id, timeout=timeout)
    result = extract_outputs(entry, base_url, output_id_to_var)
    result["prompt_id"] = prompt_id
    result["node_errors"] = node_errors
    return result


def register_routes(routes):
    @routes.get(f"{PREFIX}/ping")
    async def ping(request):
        return web.json_response({"ok": True, "service": "rest_api", "version": "0.1"})

    @routes.get(f"{PREFIX}/workflows")
    async def workflows(request):
        return web.json_response({"workflows": list_workflows(), "dir": api_workflows_dir()})

    @routes.post(f"{PREFIX}/save-workflow")
    async def save_workflow(request):
        body = await request.json()
        name = body.get("name")
        wf = body.get("workflow")
        if not name or not isinstance(wf, dict):
            return web.json_response({"error": "name and workflow (dict) required"}, status=400)
        path = save_by_name(name, wf)
        return web.json_response({"ok": True, "name": name, "path": path})

    @routes.post(f"{PREFIX}/upload")
    async def upload(request):
        base_url = build_base_url(request)
        files = await save_uploaded_files(request, base_url)
        return web.json_response({"files": files})

    @routes.post(f"{PREFIX}/execute")
    async def execute(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON body"}, status=400)

        workflow_value = body.get("workflow")
        if workflow_value is None:
            return web.json_response({"error": "'workflow' is required"}, status=400)

        params = body.get("params") or {}
        wait_for_result = body.get("wait_for_result", True)
        timeout = float(body.get("timeout", 300))
        base_url = build_base_url(request)

        try:
            prompt, output_id_to_var = await _prepare_prompt(workflow_value, params)
        except FileNotFoundError as e:
            return web.json_response({"error": str(e)}, status=404)
        except Exception as e:
            log.exception("prepare failed")
            return web.json_response({"error": f"prepare failed: {e}"}, status=400)

        if wait_for_result:
            try:
                result = await _run_and_collect(prompt, output_id_to_var, base_url, timeout)
            except TimeoutError as e:
                return web.json_response({"error": str(e)}, status=504)
            except Exception as e:
                log.exception("execute failed")
                return web.json_response({"error": f"execute failed: {e}"}, status=500)
            result["status"] = "completed"
            return web.json_response(result)

        # Async mode
        task_id = str(uuid.uuid4())
        task_store.create(task_id)
        result_url = f"{base_url}{PREFIX}/result/{task_id}"
        log.info("[rest_api] async task %s -> GET %s", task_id, result_url)

        async def _runner():
            try:
                prompt_id, _ = await submit_prompt(prompt)
                task_store.update(task_id, prompt_id=prompt_id)
                entry = await wait_for_history(prompt_id, timeout=timeout)
                result = extract_outputs(entry, base_url, output_id_to_var)
                result["prompt_id"] = prompt_id
                task_store.update(task_id, status="completed", result=result)
            except Exception as e:
                log.exception("async task %s failed", task_id)
                task_store.update(task_id, status="failed", error=str(e))

        asyncio.create_task(_runner())

        return web.json_response({
            "task_id": task_id,
            "status": "pending",
            "result_url": result_url,
        })

    @routes.get(f"{PREFIX}/result/{{task_id}}")
    async def get_result(request):
        task_id = request.match_info["task_id"]
        task = task_store.get(task_id)
        if task is None:
            return web.json_response({"error": "task not found"}, status=404)
        resp = {"task_id": task_id, "status": task["status"]}
        if task["status"] == "completed":
            resp.update(task["result"] or {})
        elif task["status"] == "failed":
            resp["error"] = task["error"]
        else:
            resp["prompt_id"] = task.get("prompt_id")
        return web.json_response(resp)
