"""In-process task store for async executions. No persistence."""
import time
from typing import Dict, Any

_tasks: Dict[str, Dict[str, Any]] = {}


def create(task_id: str):
    _tasks[task_id] = {
        "status": "pending",
        "created_at": time.time(),
        "prompt_id": None,
        "result": None,
        "error": None,
    }


def update(task_id: str, **kwargs):
    if task_id in _tasks:
        _tasks[task_id].update(kwargs)


def get(task_id: str):
    return _tasks.get(task_id)
