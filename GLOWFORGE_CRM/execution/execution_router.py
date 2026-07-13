"""V8.3 ExecutionRouter — Thin wrapper around handler execution

将 handler 调用封装为标准接口，返回统一结果格式。
WorkerLoop 使用此 router 而非直接调用 handler，便于审计和 side-effect 追踪。

Usage:
    from execution.execution_router import ExecutionRouter
    result = ExecutionRouter.execute(handler_fn, task_payload)
    # → {"ok": bool, "result": dict, "error": str}
"""

import logging
import traceback

logger = logging.getLogger("glowforge.execution_router")


class ExecutionRouter:
    """Thin wrapper for handler execution with standardized result format."""

    @staticmethod
    def execute(handler, payload, task_dict=None):
        """Execute a handler with standardized error handling.

        Args:
            handler: callable(payload) -> dict or None
            payload: dict passed to handler
            task_dict: optional full task dict (for logging)

        Returns:
            dict with keys:
                ok: bool
                result: dict (handler return value or {})
                error: str (empty string on success)
        """
        try:
            result = handler(payload)
            return {
                "ok": True,
                "result": result or {},
                "error": "",
            }
        except Exception as e:
            error_str = f"{type(e).__name__}: {e}"[:500]
            logger.warning(
                "[ExecutionRouter] Handler failed: %s (task_type=%s)",
                error_str,
                (task_dict or {}).get("task_type", "?"),
            )
            return {
                "ok": False,
                "result": {},
                "error": error_str,
            }
