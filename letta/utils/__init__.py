"""
Letta utilities package.

This package contains utility modules for various Letta functionality.
"""

# Import functions from the main utils.py file to maintain compatibility
import sys
import os

# Add parent directory to path to import utils.py
_parent_dir = os.path.dirname(os.path.dirname(__file__))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    # Import directly from utils.py
    import importlib.util

    _utils_file_path = os.path.join(_parent_dir, "utils.py")
    _spec = importlib.util.spec_from_file_location("letta_utils_module", _utils_file_path)
    _utils_module = importlib.util.module_from_spec(_spec)
    sys.modules["letta_utils_module"] = _utils_module
    _spec.loader.exec_module(_utils_module)

    # Re-export all public functions from utils module
    for attr_name in dir(_utils_module):
        if not attr_name.startswith("_"):
            attr_value = getattr(_utils_module, attr_name)
            if callable(attr_value):
                globals()[attr_name] = attr_value

except (ImportError, AttributeError) as e:
    # Fallback implementations if import fails
    def is_valid_url(url):
        """Fallback URL validation."""
        try:
            from urllib.parse import urlparse

            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    def printd(*args, **kwargs):
        """Fallback debug print."""
        pass  # No-op for now

    def parse_json(text):
        """Fallback JSON parser."""
        import json

        return json.loads(text)

    def count_tokens(text, model="gpt-4"):
        """Fallback token counter."""
        return len(text.split())  # Very rough estimate

    def get_friendly_error_msg(error):
        """Fallback error message."""
        return str(error)

    def get_tool_call_id():
        """Fallback tool call ID."""
        import uuid

        return str(uuid.uuid4())

    def log_telemetry(*args, **kwargs):
        """Fallback telemetry logging."""
        pass

    def validate_function_response(*args, **kwargs):
        """Fallback function response validation."""
        return True


__all__ = [
    "is_valid_url",
    "printd",
    "parse_json",
    "count_tokens",
    "get_friendly_error_msg",
    "get_tool_call_id",
    "log_telemetry",
    "validate_function_response",
]
