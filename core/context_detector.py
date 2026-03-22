"""Thin wrapper around platform_utils for app-context detection in trevo."""
from __future__ import annotations

from utils.logger import logger

from utils.platform_utils import AppContext, get_active_context


class ContextDetector:
    """Detects the active application context on the user's desktop.

    This is a lightweight facade over :func:`utils.platform_utils.get_active_context`
    so that the rest of the ``core`` package can depend on a single, mockable object.
    """

    def get_active_context(self) -> AppContext:
        """Return the current :class:`AppContext` for the foreground window."""
        ctx = get_active_context()
        logger.debug(
            "Detected context: app={}, type={}, title='{}'",
            ctx.app_name,
            ctx.app_type,
            ctx.window_title[:60],
        )
        return ctx
