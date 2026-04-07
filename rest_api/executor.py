"""Submit a workflow to ComfyUI's internal queue and poll for results."""
import asyncio
import time
import uuid
import logging


async def submit_prompt(prompt: dict, client_id: str = "rest_api") -> tuple:
    """Validate + enqueue a prompt. Returns (prompt_id, node_errors)."""
    import execution
    from server import PromptServer
    server = PromptServer.instance
    prompt_id = str(uuid.uuid4())

    valid = await execution.validate_prompt(prompt_id, prompt, None)
    if not valid[0]:
        raise ValueError({"error": valid[1], "node_errors": valid[3]})

    number = server.number
    server.number += 1

    outputs_to_execute = valid[2]
    extra_data = {"client_id": client_id, "create_time": int(time.time() * 1000)}
    sensitive: dict = {}

    server.prompt_queue.put(
        (number, prompt_id, prompt, extra_data, outputs_to_execute, sensitive)
    )
    return prompt_id, valid[3]


async def wait_for_history(prompt_id: str, timeout: float = 300.0, interval: float = 0.3) -> dict:
    """Poll prompt_queue.get_history until this prompt_id appears or timeout."""
    from server import PromptServer
    server = PromptServer.instance
    deadline = time.monotonic() + timeout
    while True:
        hist = server.prompt_queue.get_history(prompt_id=prompt_id)
        if hist and prompt_id in hist:
            entry = hist[prompt_id]
            status = (entry.get("status") or {})
            # ComfyUI marks status.completed bool and status_str
            if status.get("completed") is True or entry.get("outputs"):
                return entry
            status_str = status.get("status_str")
            if status_str == "error":
                raise RuntimeError(f"execution failed: {status}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"timeout waiting for prompt {prompt_id}")
        await asyncio.sleep(interval)
