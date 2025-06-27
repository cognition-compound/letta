import logging
from logging.config import dictConfig
from pathlib import Path
from sys import stdout
from typing import Optional

from letta.settings import settings

selected_log_level = logging.DEBUG if settings.debug else logging.INFO


def _has_json_logger() -> bool:
    """Check if python-json-logger is available for structured logging"""
    try:
        import pythonjsonlogger.jsonlogger
        return True
    except ImportError:
        return False


def _setup_logfile() -> "Path":
    """ensure the logger filepath is in place

    Returns: the logfile Path
    """
    logfile = Path(settings.letta_dir / "logs" / "Letta.log")
    logfile.parent.mkdir(parents=True, exist_ok=True)
    logfile.touch(exist_ok=True)
    return logfile


def _setup_audit_logfile() -> "Path":
    """ensure the audit logger filepath is in place

    Returns: the audit logfile Path
    """
    audit_logfile = Path(settings.letta_dir / "logs" / "audit.log")
    audit_logfile.parent.mkdir(parents=True, exist_ok=True)
    audit_logfile.touch(exist_ok=True)
    return audit_logfile


PRODUCTION_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d"
        } if _has_json_logger() else {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "console": {
            "format": "%(levelname)s: %(message)s"
        }
    },
    "handlers": {
        "console": {
            "level": "WARNING",  # Only warnings and above to stdout in production
            "class": "logging.StreamHandler",
            "stream": stdout,
            "formatter": "console",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler", 
            "filename": _setup_logfile(),
            "maxBytes": 1024**2 * 100,  # 100MB files in production
            "backupCount": 30,  # Keep 30 days worth of logs (assuming ~1 file per day)
            "formatter": "json" if _has_json_logger() else "standard",  # Structured logging for production
            "encoding": "utf-8",
        },
        "audit": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": _setup_audit_logfile(),
            "maxBytes": 1024**2 * 50,  # 50MB for audit logs
            "backupCount": 90,  # Keep audit logs for 90 days
            "formatter": "json" if _has_json_logger() else "standard",
            "encoding": "utf-8",
        },
    },
    "root": {
        "level": "INFO",  # INFO and above in production
        "handlers": ["console", "file"],
    },
    "loggers": {
        "Letta": {
            "level": "INFO",
            "propagate": True,
        },
        "uvicorn": {
            "level": "WARNING",  # Reduce uvicorn noise in production
            "handlers": ["console"],
            "propagate": True,
        },
        "uvicorn.access": {
            "level": "WARNING",  # Disable access logs in production (use middleware instead)
            "propagate": False,
        },
        "sqlalchemy.engine": {
            "level": "WARNING",  # Reduce SQL query noise in production
            "propagate": True,
        },
        "httpx": {
            "level": "WARNING",  # Reduce HTTP client noise
            "propagate": True,
        },
        "Letta.audit": {
            "level": "INFO",
            "handlers": ["audit"],
            "propagate": False,  # Don't propagate audit logs to main log
        },
    },
}

DEVELOPMENT_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,  # Allow capturing from all loggers
    "formatters": {
        "standard": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
        "no_datetime": {"format": "%(name)s - %(levelname)s - %(message)s"},
    },
    "handlers": {
        "console": {
            "level": selected_log_level,
            "class": "logging.StreamHandler",
            "stream": stdout,
            "formatter": "no_datetime",
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": _setup_logfile(),
            "maxBytes": 1024**2 * 10,  # 10MB for development
            "backupCount": 3,
            "formatter": "standard",
            "encoding": "utf-8",
        },
        "audit": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": _setup_audit_logfile(),
            "maxBytes": 1024**2 * 5,  # 5MB for dev audit logs
            "backupCount": 5,
            "formatter": "standard",
            "encoding": "utf-8",
        },
    },
    "root": {  # Root logger handles all logs
        "level": logging.DEBUG if settings.debug else logging.INFO,
        "handlers": ["console", "file"],
    },
    "loggers": {
        "Letta": {
            "level": logging.DEBUG if settings.debug else logging.INFO,
            "propagate": True,  # Let logs bubble up to root
        },
        "uvicorn": {
            "level": "CRITICAL",
            "handlers": ["console"],
            "propagate": True,
        },
        "Letta.audit": {
            "level": "INFO",
            "handlers": ["audit"],
            "propagate": False,  # Don't propagate audit logs to main log
        },
    },
}


_logging_configured = False

def get_logger(name: Optional[str] = None) -> "logging.Logger":
    """returns the project logger, scoped to a child name if provided
    Args:
        name: will define a child logger
    """
    global _logging_configured
    
    # Only configure logging once to avoid repeated configuration
    if not _logging_configured:
        # Use production logging config when debug=False, development config when debug=True
        config = DEVELOPMENT_LOGGING if settings.debug else PRODUCTION_LOGGING
        try:
            dictConfig(config)
            _logging_configured = True
        except Exception as e:
            # Fallback to basic configuration if structured logging fails
            logging.basicConfig(
                level=logging.DEBUG if settings.debug else logging.INFO,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            logging.getLogger(__name__).warning(f"Failed to configure advanced logging, using basic config: {e}")
            _logging_configured = True
    
    parent_logger = logging.getLogger("Letta")
    if name:
        return parent_logger.getChild(name)
    return parent_logger


def get_audit_logger() -> "logging.Logger":
    """Get the dedicated audit logger for security events."""
    global _logging_configured
    
    # Ensure logging is configured
    if not _logging_configured:
        get_logger()  # This will configure logging
    
    return logging.getLogger("Letta.audit")
