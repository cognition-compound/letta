import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from letta.log import get_logger
from letta.server.rest_api.interface import QueuingInterface
from letta.server.server import SyncServer

logger = get_logger(__name__)
router = APIRouter()


class AuthResponse(BaseModel):
    uuid: UUID = Field(..., description="UUID of the user")
    is_admin: Optional[bool] = Field(None, description="Whether the user is an admin")


class AuthRequest(BaseModel):
    password: str = Field(None, description="Admin password provided when starting the Letta server")


def setup_auth_router(server: SyncServer, interface: QueuingInterface, password: str) -> APIRouter:

    @router.post("/auth", tags=["auth"], response_model=AuthResponse)
    def authenticate_user(auth_request: AuthRequest, request: Request) -> AuthResponse:
        """
        Authenticates the user and sends response with User related data.

        Currently, this is a placeholder that simply returns a UUID placeholder
        """
        start_time = time.time()
        client_ip = _get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        request_id = getattr(request.state, "request_id", "unknown")

        interface.clear()

        try:
            is_admin = False
            if auth_request.password != password:
                # API key authentication attempt
                response = server.api_key_to_user(api_key=auth_request.password)
                credential_type = "api_key"
            else:
                # Admin password authentication
                is_admin = True
                response = server.authenticate_user()
                credential_type = "admin_password"

            # Log successful authentication
            logger.info(
                f"Endpoint authentication successful",
                extra={
                    "event_type": "auth_endpoint_success",
                    "credential_type": credential_type,
                    "user_id": str(response),
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "request_id": request_id,
                    "auth_duration_ms": round((time.time() - start_time) * 1000, 2),
                    "is_admin": is_admin,
                    "endpoint": "/auth",
                },
            )

            return AuthResponse(uuid=response, is_admin=is_admin)

        except Exception as e:
            # Log failed authentication attempt
            logger.warning(
                f"Endpoint authentication failed: {str(e)}",
                extra={
                    "event_type": "auth_endpoint_failure",
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "request_id": request_id,
                    "auth_duration_ms": round((time.time() - start_time) * 1000, 2),
                    "endpoint": "/auth",
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    return router


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request headers."""
    # Check for forwarded headers first (for load balancers/proxies)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip

    # Fallback to direct client
    if request.client:
        return request.client.host

    return "unknown"
