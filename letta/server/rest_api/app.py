import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from letta.server.rest_api.middleware import RequestLoggingMiddleware, UserContextMiddleware

from letta.__init__ import __version__
from letta.agents.exceptions import IncompatibleAgentType
from letta.constants import ADMIN_PREFIX, API_PREFIX, OPENAI_API_PREFIX
from letta.errors import BedrockPermissionError, LettaAgentNotFoundError, LettaUserNotFoundError
from letta.log import get_logger
from letta.orm.errors import DatabaseTimeoutError, ForeignKeyConstraintViolationError, NoResultFound, UniqueConstraintViolationError
from letta.schemas.letta_message import create_letta_message_union_schema
from letta.schemas.letta_message_content import (
    create_letta_assistant_message_content_union_schema,
    create_letta_message_content_union_schema,
    create_letta_user_message_content_union_schema,
)
from letta.server.constants import REST_DEFAULT_PORT

# NOTE(charles): these are extra routes that are not part of v1 but we still need to mount to pass tests
from letta.server.rest_api.auth.index import setup_auth_router  # TODO: probably remove right?
from letta.server.rest_api.interface import StreamingServerInterface
from letta.server.rest_api.routers.openai.chat_completions.chat_completions import router as openai_chat_completions_router

# from letta.orm.utilities import get_db_session  # TODO(ethan) reenable once we merge ORM
from letta.server.rest_api.routers.v1 import ROUTERS as v1_routes
from letta.server.rest_api.routers.v1.organizations import router as organizations_router
from letta.server.rest_api.routers.v1.users import router as users_router  # TODO: decide on admin
from letta.server.rest_api.static_files import mount_static_files
from letta.server.server import SyncServer
from letta.settings import settings

# TODO(ethan)
# NOTE(charles): @ethan I had to add this to get the global as the bottom to work
interface: StreamingServerInterface = StreamingServerInterface
server = SyncServer(default_interface_factory=lambda: interface())
logger = get_logger(__name__)


import logging
import platform

from fastapi import FastAPI

is_windows = platform.system() == "Windows"

from letta.log import get_logger
log = get_logger("uvicorn")


def generate_openapi_schema(app: FastAPI):
    # Update the OpenAPI schema
    if not app.openapi_schema:
        app.openapi_schema = app.openapi()

    letta_docs = app.openapi_schema.copy()
    letta_docs["paths"] = {k: v for k, v in letta_docs["paths"].items() if not k.startswith("/openai")}
    letta_docs["info"]["title"] = "Letta API"
    letta_docs["components"]["schemas"]["LettaMessageUnion"] = create_letta_message_union_schema()
    letta_docs["components"]["schemas"]["LettaMessageContentUnion"] = create_letta_message_content_union_schema()
    letta_docs["components"]["schemas"]["LettaAssistantMessageContentUnion"] = create_letta_assistant_message_content_union_schema()
    letta_docs["components"]["schemas"]["LettaUserMessageContentUnion"] = create_letta_user_message_content_union_schema()

    # Update the app's schema with our modified version
    app.openapi_schema = letta_docs

    for name, docs in [
        (
            "letta",
            letta_docs,
        ),
    ]:
        if settings.cors_origins:
            docs["servers"] = [{"url": host} for host in settings.cors_origins]
        # Write OpenAPI schema to a writable directory
        import os

        openapi_dir = os.environ.get("LETTA_OPENAPI_DIR", "/tmp")
        openapi_path = Path(openapi_dir) / f"openapi_{name}.json"
        openapi_path.write_text(json.dumps(docs, indent=2))


# middleware that only allows requests to pass through if user provides a password thats randomly generated and stored in memory
def generate_password():
    import secrets

    return secrets.token_urlsafe(16)


random_password = os.getenv("LETTA_SERVER_PASSWORD") or generate_password()


class CheckPasswordMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):

        # Exclude health check endpoint from password protection
        if request.url.path in {"/v1/health", "/v1/health/", "/latest/health/"}:
            return await call_next(request)

        if (
            request.headers.get("X-BARE-PASSWORD") == f"password {random_password}"
            or request.headers.get("Authorization") == f"Bearer {random_password}"
        ):
            return await call_next(request)

        return JSONResponse(
            content={"detail": "Unauthorized"},
            status_code=401,
        )


def _get_client_ip_for_error(request: Request) -> str:
    """Extract client IP from request for error logging."""
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


def create_application() -> "FastAPI":
    """the application start routine"""
    # global server
    # server = SyncServer(default_interface_factory=lambda: interface())
    log.info(f"Starting Letta server v{__version__}")

    if (os.getenv("SENTRY_DSN") is not None) and (os.getenv("SENTRY_DSN") != ""):
        import sentry_sdk

        sentry_sdk.init(
            dsn=os.getenv("SENTRY_DSN"),
            traces_sample_rate=1.0,
            _experiments={
                "continuous_profiling_auto_start": True,
            },
        )

    debug_mode = "--debug" in sys.argv
    app = FastAPI(
        swagger_ui_parameters={"docExpansion": "none"},
        # openapi_tags=TAGS_METADATA,
        title="Letta",
        summary="Create LLM agents with long-term memory and custom tools 📚🦙",
        version="1.0.0",  # TODO wire this up to the version in the package
        debug=debug_mode,  # if True, the stack trace will be printed in the response
    )

    @app.exception_handler(IncompatibleAgentType)
    async def handle_incompatible_agent_type(request: Request, exc: IncompatibleAgentType):
        # Extract request context for error logging
        request_id = getattr(request.state, "request_id", "unknown")
        user_id = getattr(request.state, "user_id", None)
        client_ip = _get_client_ip_for_error(request)
        
        # Log the agent type error with context
        log.warning(
            f"Incompatible agent type error: {str(exc)} (req_id: {request_id})",
            extra={
                "error_type": "IncompatibleAgentType",
                "expected_type": exc.expected_type,
                "actual_type": exc.actual_type,
                "request_id": request_id,
                "user_id": str(user_id) if user_id else None,
                "client_ip": client_ip,
                "method": request.method,
                "path": request.url.path,
            }
        )
        
        return JSONResponse(
            status_code=400,
            content={
                "detail": str(exc),
                "expected_type": exc.expected_type,
                "actual_type": exc.actual_type,
                "request_id": request_id,  # Include request ID in response for traceability
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        import traceback
        
        # Extract request context for error logging
        request_id = getattr(request.state, "request_id", "unknown")
        user_id = getattr(request.state, "user_id", None)
        organization_id = getattr(request.state, "organization_id", None)
        client_ip = _get_client_ip_for_error(request)
        user_agent = request.headers.get("user-agent", "")
        method = request.method
        url = str(request.url)
        
        # Create structured error context
        error_context = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "request_id": request_id,
            "method": method,
            "url": url,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "user_id": str(user_id) if user_id else None,
            "organization_id": str(organization_id) if organization_id else None,
            "stack_trace": traceback.format_exc(),
        }
        
        # Log with full context
        log.error(
            f"Unhandled error: {str(exc)} (req_id: {request_id})",
            extra=error_context,
            exc_info=True
        )

        if (os.getenv("SENTRY_DSN") is not None) and (os.getenv("SENTRY_DSN") != ""):
            import sentry_sdk
            
            # Add context to Sentry
            with sentry_sdk.configure_scope() as scope:
                scope.set_tag("request_id", request_id)
                scope.set_user({"id": user_id, "organization_id": organization_id})
                scope.set_context("request", {
                    "method": method,
                    "url": url,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                })
            
            sentry_sdk.capture_exception(exc)

        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal server error occurred",
                "request_id": request_id,  # Include request ID for traceability
                # Only include error details in debug/development mode
                "debug_info": str(exc) if settings.debug else None,
            },
        )

    @app.exception_handler(NoResultFound)
    async def no_result_found_handler(request: Request, exc: NoResultFound):
        logger.error(f"NoResultFound: {exc}")

        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ForeignKeyConstraintViolationError)
    async def foreign_key_constraint_handler(request: Request, exc: ForeignKeyConstraintViolationError):
        logger.error(f"ForeignKeyConstraintViolationError: {exc}")

        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(UniqueConstraintViolationError)
    async def unique_key_constraint_handler(request: Request, exc: UniqueConstraintViolationError):
        logger.error(f"UniqueConstraintViolationError: {exc}")

        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(DatabaseTimeoutError)
    async def database_timeout_error_handler(request: Request, exc: DatabaseTimeoutError):
        logger.error(f"Timeout occurred: {exc}. Original exception: {exc.original_exception}")
        return JSONResponse(
            status_code=503,
            content={"detail": "The database is temporarily unavailable. Please try again later."},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(LettaAgentNotFoundError)
    async def agent_not_found_handler(request: Request, exc: LettaAgentNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Agent not found"})

    @app.exception_handler(LettaUserNotFoundError)
    async def user_not_found_handler(request: Request, exc: LettaUserNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "User not found"})

    @app.exception_handler(BedrockPermissionError)
    async def bedrock_permission_error_handler(request, exc: BedrockPermissionError):
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "type": "bedrock_permission_denied",
                    "message": "Unable to access the required AI model. Please check your Bedrock permissions or contact support.",
                    "details": {"model_arn": exc.model_arn, "reason": str(exc)},
                }
            },
        )

    settings.cors_origins.append("https://app.letta.com")

    if (os.getenv("LETTA_SERVER_SECURE") == "true") or "--secure" in sys.argv:
        log.info(f"Using secure mode with password: {random_password}")
        app.add_middleware(CheckPasswordMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add user context middleware (must be before logging middleware)
    app.add_middleware(UserContextMiddleware)
    
    # Add request logging middleware for comprehensive HTTP tracking
    app.add_middleware(
        RequestLoggingMiddleware,
        log_level="DEBUG" if settings.debug else "INFO",
        log_request_body=settings.debug,  # Only log request bodies in debug mode
        log_response_body=False,  # Response body logging disabled for performance
        max_body_size=2048,  # Limit body logging to 2KB
        skip_paths={"/v1/health", "/health", "/metrics", "/favicon.ico", "/docs", "/redoc", "/openapi.json"},
    )

    # Set up OpenTelemetry based on standard environment variables
    if not settings.disable_tracing:
        # Only set OTEL_SERVICE_NAME if not already provided - respect explicit configuration
        if not os.environ.get("OTEL_SERVICE_NAME"):
            # Fallback: use ENV_NAME suffix for multi-tenant deployments
            env_name_suffix = os.getenv("ENV_NAME")
            service_name = f"letta-server-{env_name_suffix.lower()}" if env_name_suffix else "letta-server"
            os.environ["OTEL_SERVICE_NAME"] = service_name

        from letta.otel.logging import setup_logging
        from letta.otel.metrics import setup_metrics
        from letta.otel.tracing import setup_tracing

        # Set up OpenTelemetry using standard configuration
        setup_tracing(app=app)
        setup_metrics(app=app)
        setup_logging()

        log.info(f"OpenTelemetry configured for service: {os.environ.get('OTEL_SERVICE_NAME')}")

    for route in v1_routes:
        app.include_router(route, prefix=API_PREFIX)
        # this gives undocumented routes for "latest" and bare api calls.
        # we should always tie this to the newest version of the api.
        # app.include_router(route, prefix="", include_in_schema=False)
        app.include_router(route, prefix="/latest", include_in_schema=False)

    # NOTE: ethan these are the extra routes
    # TODO(ethan) remove

    # admin/users
    app.include_router(users_router, prefix=ADMIN_PREFIX)
    app.include_router(organizations_router, prefix=ADMIN_PREFIX)

    # openai
    app.include_router(openai_chat_completions_router, prefix=OPENAI_API_PREFIX)

    # /api/auth endpoints
    app.include_router(setup_auth_router(server, interface, random_password), prefix=API_PREFIX)

    # / static files
    mount_static_files(app)

    # Generate OpenAPI schema after all routes are mounted
    generate_openapi_schema(app)

    return app


app = create_application()


def start_server(
    port: Optional[int] = None,
    host: Optional[str] = None,
    debug: bool = False,
    reload: bool = False,
):
    """Convenience method to start the server from within Python"""
    if debug:
        from letta.server.server import logger as server_logger

        # Set the logging level
        server_logger.setLevel(logging.DEBUG)
        # Create a StreamHandler
        stream_handler = logging.StreamHandler()
        # Set the formatter (optional)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        stream_handler.setFormatter(formatter)
        # Add the handler to the logger
        server_logger.addHandler(stream_handler)

    # Experimental UV Loop Support
    try:
        if importlib.util.find_spec("uvloop") is not None and settings.use_uvloop:
            log.info("Running server on uvloop")
            import asyncio

            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except:
        pass

    if (os.getenv("LOCAL_HTTPS") == "true") or "--localhttps" in sys.argv:
        log.info(f"Server running at: https://{host or 'localhost'}:{port or REST_DEFAULT_PORT}")
        log.info(f"View using ADE at: https://app.letta.com/development-servers/local/dashboard")
        if importlib.util.find_spec("granian") is not None and settings.use_granian:
            from granian import Granian

            # Experimental Granian engine
            Granian(
                target="letta.server.rest_api.app:app",
                # factory=True,
                interface="asgi",
                address=host or "127.0.0.1",  # Note granian address must be an ip address
                port=port or REST_DEFAULT_PORT,
                workers=settings.uvicorn_workers,
                # threads=
                reload=reload or settings.uvicorn_reload,
                reload_ignore_patterns=["openapi_letta.json"],
                reload_ignore_worker_failure=True,
                reload_tick=4000,  # set to 4s to prevent crashing on weird state
                # log_level="info"
                ssl_keyfile="certs/localhost-key.pem",
                ssl_cert="certs/localhost.pem",
            ).serve()
        else:
            uvicorn.run(
                "letta.server.rest_api.app:app",
                host=host or "localhost",
                port=port or REST_DEFAULT_PORT,
                workers=settings.uvicorn_workers,
                reload=reload or settings.uvicorn_reload,
                timeout_keep_alive=settings.uvicorn_timeout_keep_alive,
                ssl_keyfile="certs/localhost-key.pem",
                ssl_certfile="certs/localhost.pem",
            )

    else:
        if is_windows:
            # Windows doesn't those the fancy unicode characters
            log.info(f"Server running at: http://{host or 'localhost'}:{port or REST_DEFAULT_PORT}")
            log.info(f"View using ADE at: https://app.letta.com/development-servers/local/dashboard")
        else:
            log.info(f"Server running at: http://{host or 'localhost'}:{port or REST_DEFAULT_PORT}")
            log.info(f"View using ADE at: https://app.letta.com/development-servers/local/dashboard")

        if importlib.util.find_spec("granian") is not None and settings.use_granian:
            # Experimental Granian engine
            from granian import Granian

            Granian(
                target="letta.server.rest_api.app:app",
                # factory=True,
                interface="asgi",
                address=host or "127.0.0.1",  # Note granian address must be an ip address
                port=port or REST_DEFAULT_PORT,
                workers=settings.uvicorn_workers,
                # runtime_blocking_threads=
                # runtime_threads=
                reload=reload or settings.uvicorn_reload,
                reload_paths=["../letta/"],
                reload_ignore_worker_failure=True,
                reload_tick=4000,  # set to 4s to prevent crashing on weird state
                # log_level="info"
            ).serve()
        else:
            uvicorn.run(
                "letta.server.rest_api.app:app",
                host=host or "localhost",
                port=port or REST_DEFAULT_PORT,
                workers=settings.uvicorn_workers,
                reload=reload or settings.uvicorn_reload,
                timeout_keep_alive=settings.uvicorn_timeout_keep_alive,
            )
