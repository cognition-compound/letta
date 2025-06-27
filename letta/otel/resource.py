import os
import sys
import uuid

from opentelemetry.sdk.resources import Resource

from letta import __version__ as letta_version

_resources = {}


def get_resource() -> Resource:
    """Get OpenTelemetry resource using standard OTEL_SERVICE_NAME environment variable."""
    service_name = os.environ.get("OTEL_SERVICE_NAME", "letta-server")
    _env = os.getenv("LETTA_ENVIRONMENT")
    
    cache_key = (service_name, _env)
    if cache_key not in _resources:
        resource_dict = {
            "service.name": service_name,
            "letta.version": letta_version,
        }
        if _env != "PRODUCTION":
            resource_dict["device.id"] = str(uuid.getnode())  # MAC address as unique device identifier,
        
        # Create resource and merge with any OTEL_RESOURCE_ATTRIBUTES
        resource = Resource.create(resource_dict)
        _resources[cache_key] = resource
    
    return _resources[cache_key]


def is_pytest_environment():
    return "pytest" in sys.modules
