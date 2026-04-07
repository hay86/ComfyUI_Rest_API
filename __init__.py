"""ComfyUI_Rest_API - expose ComfyUI workflows as simple REST APIs."""
import logging

from .rest_api.routes import register_routes

try:
    from server import PromptServer
    register_routes(PromptServer.instance.routes)
    logging.info("[rest_api] routes registered under /rest/v1/")
except Exception as e:
    logging.exception("[rest_api] failed to register routes: %s", e)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
