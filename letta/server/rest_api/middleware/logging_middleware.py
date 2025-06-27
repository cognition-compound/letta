import time
import uuid
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from letta.log import get_logger
from letta.server.rest_api.utils import LoggingSanitizer

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive HTTP request/response logging and tracking."""
    
    def __init__(
        self,
        app: ASGIApp,
        log_level: str = "INFO",
        log_request_body: bool = False,
        log_response_body: bool = False,
        max_body_size: int = 1024,  # Max body size to log in bytes
        skip_paths: Optional[set] = None,
    ):
        super().__init__(app)
        self.log_level = log_level.upper()
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.max_body_size = max_body_size
        self.skip_paths = skip_paths or {"/v1/health", "/health", "/metrics", "/favicon.ico"}
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for certain paths
        if request.url.path in self.skip_paths:
            return await call_next(request)
            
        # Generate unique request ID for correlation
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Start timing
        start_time = time.time()
        
        # Extract request information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        content_length = request.headers.get("content-length", 0)
        method = request.method
        url = str(request.url)
        
        # Extract user information if available (will be set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        organization_id = getattr(request.state, "organization_id", None)
        
        # Try to extract from headers if not in state (for API key auth)
        if not user_id:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                # Store token info for potential user lookup in dependencies
                request.state.auth_token = auth_header[7:]
        
        # Log request with sanitized data
        request_data = {
            "request_id": request_id,
            "method": method,
            "url": LoggingSanitizer.sanitize_string(url),
            "path": request.url.path,
            "query_params": LoggingSanitizer.sanitize_query_params(dict(request.query_params)),
            "client_ip": client_ip,
            "user_agent": LoggingSanitizer.sanitize_string(user_agent),
            "content_length": content_length,
            "user_id": user_id,
            "organization_id": organization_id,
        }
        
        # Add request body if enabled and appropriate
        if self.log_request_body and method in ["POST", "PUT", "PATCH"]:
            request_data["request_body"] = await self._get_request_body(request)
            
        self._log_request(request_data)
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate response time
            process_time = time.time() - start_time
            
            # Extract response information
            response_data = {
                "request_id": request_id,
                "status_code": response.status_code,
                "response_time_ms": round(process_time * 1000, 2),
                "response_size": response.headers.get("content-length", 0),
                "user_id": user_id,
                "organization_id": organization_id,
            }
            
            # Add response body if enabled and appropriate
            if self.log_response_body and response.status_code >= 400:
                response_data["response_body"] = await self._get_response_body(response)
                
            self._log_response(response_data)
            
            # Add request ID to response headers for traceability
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Log failed requests
            process_time = time.time() - start_time
            
            error_data = {
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "response_time_ms": round(process_time * 1000, 2),
                "user_id": user_id,
                "organization_id": organization_id,
            }
            
            self._log_error(error_data)
            raise
    
    def _get_client_ip(self, request: Request) -> str:
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
    
    async def _get_request_body(self, request: Request) -> str:
        """Safely extract and sanitize request body for logging."""
        try:
            body = await request.body()
            if len(body) > self.max_body_size:
                return f"<body too large: {len(body)} bytes>"
            
            raw_body = body.decode("utf-8", errors="ignore")[:self.max_body_size]
            content_type = request.headers.get("content-type", "")
            
            # Sanitize the body content
            sanitized_body = LoggingSanitizer.sanitize_request_body(raw_body, content_type)
            return sanitized_body
        except Exception:
            return "<unable to read body>"
    
    async def _get_response_body(self, response: Response) -> str:
        """Safely extract response body for logging."""
        try:
            # This is complex for streaming responses, simplified for now
            return "<response body logging not fully implemented>"
        except Exception:
            return "<unable to read response body>"
    
    def _log_request(self, data: dict) -> None:
        """Log incoming request."""
        if self.log_level == "DEBUG":
            logger.debug(f"HTTP Request: {data['method']} {data['path']}", extra=data)
        else:
            logger.info(
                f"HTTP {data['method']} {data['path']} from {data['client_ip']} "
                f"(user: {data['user_id']}, req_id: {data['request_id']})",
                extra=data
            )
    
    def _log_response(self, data: dict) -> None:
        """Log outgoing response."""
        status = data['status_code']
        time_ms = data['response_time_ms']
        
        if status >= 500:
            logger.error(f"HTTP {status} in {time_ms}ms (req_id: {data['request_id']})", extra=data)
        elif status >= 400:
            logger.warning(f"HTTP {status} in {time_ms}ms (req_id: {data['request_id']})", extra=data)
        elif time_ms > 5000:  # Slow request threshold
            logger.warning(f"Slow HTTP {status} in {time_ms}ms (req_id: {data['request_id']})", extra=data)
        else:
            if self.log_level == "DEBUG":
                logger.debug(f"HTTP {status} in {time_ms}ms (req_id: {data['request_id']})", extra=data)
            else:
                logger.info(f"HTTP {status} in {time_ms}ms (req_id: {data['request_id']})", extra=data)
    
    def _log_error(self, data: dict) -> None:
        """Log request processing errors."""
        logger.error(
            f"HTTP request failed: {data['error_type']} in {data['response_time_ms']}ms "
            f"(req_id: {data['request_id']})",
            extra=data
        )