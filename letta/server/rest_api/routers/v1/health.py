from typing import TYPE_CHECKING, Dict, Any

from fastapi import APIRouter, Request

from letta import __version__
from letta.schemas.health import Health

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/health", tags=["health"])


# Health check
@router.get("/", response_model=Health, operation_id="health_check")
def health_check():
    return Health(
        version=__version__,
        status="ok",
    )


# Log sampling statistics
@router.get("/log-sampling-stats", operation_id="get_log_sampling_stats")
def get_log_sampling_stats(request: Request) -> Dict[str, Any]:
    """Get current log sampling statistics from the middleware."""
    try:
        # Access the middleware from the app
        for middleware in request.app.middleware_stack:
            # Check if this is our RequestLoggingMiddleware
            if hasattr(middleware, 'cls') and middleware.cls.__name__ == "RequestLoggingMiddleware":
                if hasattr(middleware, 'kwargs') and 'app' in middleware.kwargs:
                    # Get the middleware instance
                    middleware_instance = None
                    for attr_name in dir(middleware):
                        attr = getattr(middleware, attr_name)
                        if hasattr(attr, 'get_sampling_stats'):
                            middleware_instance = attr
                            break
                    
                    if middleware_instance:
                        return {
                            "status": "ok",
                            "sampling_enabled": True,
                            "stats": middleware_instance.get_sampling_stats()
                        }
        
        # If we can't find the middleware or it doesn't have sampling
        return {
            "status": "ok", 
            "sampling_enabled": False,
            "message": "Log sampling middleware not found or not configured"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get sampling stats: {str(e)}"
        }
