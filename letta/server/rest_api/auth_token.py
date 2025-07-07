import uuid
import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from letta.log import get_logger
from letta.server.rest_api.middleware import set_user_context
from letta.server.server import SyncServer

logger = get_logger(__name__)

security = HTTPBearer()


def get_current_user(
    server: SyncServer, password: str, auth: HTTPAuthorizationCredentials = Depends(security), request: Request = None
) -> uuid.UUID:
    start_time = time.time()
    client_ip = _get_client_ip(request) if request else "unknown"
    user_agent = request.headers.get("user-agent", "") if request else ""
    request_id = getattr(request.state, "request_id", "unknown") if request else "unknown"

    credential_type = "unknown"
    try:
        api_key_or_password = auth.credentials

        if api_key_or_password == password:
            # Admin authentication
            credential_type = "admin_password"
            user_id = server.authenticate_user()

            logger.info(
                f"Admin authentication successful",
                extra={
                    "event_type": "auth_success",
                    "credential_type": credential_type,
                    "user_id": str(user_id),
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "request_id": request_id,
                    "auth_duration_ms": round((time.time() - start_time) * 1000, 2),
                    "is_admin": True,
                },
            )

            # Set user context for downstream middleware and handlers
            if request:
                set_user_context(request, user_id, is_admin=True)

            return user_id
        else:
            # API key authentication
            credential_type = "api_key"
            user_id = server.api_key_to_user(api_key=api_key_or_password)

            logger.info(
                f"API key authentication successful",
                extra={
                    "event_type": "auth_success",
                    "credential_type": credential_type,
                    "user_id": str(user_id),
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "request_id": request_id,
                    "auth_duration_ms": round((time.time() - start_time) * 1000, 2),
                    "is_admin": False,
                },
            )

            # Set user context for downstream middleware and handlers
            if request:
                set_user_context(request, user_id, is_admin=False)

            return user_id

    except HTTPException as e:
        # Authentication failure
        logger.warning(
            f"Authentication failed: {e.detail}",
            extra={
                "event_type": "auth_failure",
                "credential_type": credential_type,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "request_id": request_id,
                "auth_duration_ms": round((time.time() - start_time) * 1000, 2),
                "status_code": e.status_code,
                "failure_reason": e.detail,
            },
        )
        raise
    except Exception as e:
        # Unexpected authentication error
        logger.error(
            f"Authentication error: {str(e)}",
            extra={
                "event_type": "auth_error",
                "credential_type": credential_type,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "request_id": request_id,
                "auth_duration_ms": round((time.time() - start_time) * 1000, 2),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(status_code=403, detail=f"Authentication error: {e}")


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request headers."""
    if not request:
        return "unknown"

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
