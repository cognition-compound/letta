"""Middleware for extracting and propagating user context throughout the request."""

import uuid
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from letta.log import get_logger

logger = get_logger(__name__)


class UserContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and propagate user context from authentication."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Initialize context storage
        request.state.user_id = None
        request.state.organization_id = None
        request.state.is_admin = False

        # Process the request
        response = await call_next(request)

        return response


def set_user_context(request: Request, user_id: uuid.UUID, organization_id: Optional[uuid.UUID] = None, is_admin: bool = False):
    """Helper function to set user context in request state."""
    request.state.user_id = user_id
    request.state.organization_id = organization_id
    request.state.is_admin = is_admin

    # Log context setting for debugging
    logger.debug(
        f"User context set for request",
        extra={
            "request_id": getattr(request.state, "request_id", "unknown"),
            "user_id": str(user_id),
            "organization_id": str(organization_id) if organization_id else None,
            "is_admin": is_admin,
        },
    )


def get_user_context(request: Request) -> dict:
    """Helper function to get user context from request state."""
    return {
        "user_id": getattr(request.state, "user_id", None),
        "organization_id": getattr(request.state, "organization_id", None),
        "is_admin": getattr(request.state, "is_admin", False),
        "request_id": getattr(request.state, "request_id", "unknown"),
    }
