"""Utilities for sanitizing sensitive data in logs."""

import re
from typing import Any, Dict, List, Union


class LoggingSanitizer:
    """Sanitizer for removing sensitive data from logs."""
    
    # Patterns for sensitive data
    SENSITIVE_PATTERNS = {
        'api_key': re.compile(r'(api[_-]?key|apikey|token|bearer)\s*[=:]\s*[\'"]?([a-zA-Z0-9_-]{20,})[\'"]?', re.IGNORECASE),
        'password': re.compile(r'(password|passwd|pwd)\s*[=:]\s*[\'"]?([^\s\'"]{4,})[\'"]?', re.IGNORECASE),
        'authorization': re.compile(r'(authorization|auth)\s*[=:]\s*[\'"]?(bearer\s+[a-zA-Z0-9_-]{20,}|basic\s+[a-zA-Z0-9+/=]+)[\'"]?', re.IGNORECASE),
        'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        'credit_card': re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        'ssn': re.compile(r'\b\d{3}-?\d{2}-?\d{4}\b'),
        'phone': re.compile(r'\b\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b'),
    }
    
    # Fields that should be completely removed or masked
    SENSITIVE_FIELD_NAMES = {
        'password', 'passwd', 'pwd', 'secret', 'token', 'api_key', 'apikey',
        'authorization', 'auth', 'credential', 'private_key', 'secret_key',
        'access_token', 'refresh_token', 'session_id', 'csrf_token'
    }
    
    # Headers that should be sanitized
    SENSITIVE_HEADERS = {
        'authorization', 'cookie', 'set-cookie', 'x-api-key', 'x-auth-token',
        'x-csrf-token', 'x-session-id'
    }
    
    @classmethod
    def sanitize_string(cls, text: str) -> str:
        """Sanitize sensitive data from a string."""
        if not isinstance(text, str):
            return text
            
        sanitized = text
        
        # Apply all patterns
        for pattern_name, pattern in cls.SENSITIVE_PATTERNS.items():
            sanitized = pattern.sub(cls._mask_match, sanitized)
        
        return sanitized
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], max_depth: int = 5) -> Dict[str, Any]:
        """Sanitize sensitive data from a dictionary."""
        if max_depth <= 0:
            return {"...": "max_depth_reached"}
            
        if not isinstance(data, dict):
            return data
            
        sanitized = {}
        
        for key, value in data.items():
            sanitized_key = key.lower()
            
            # Check if field name is sensitive
            if any(sensitive in sanitized_key for sensitive in cls.SENSITIVE_FIELD_NAMES):
                sanitized[key] = cls._mask_value(value)
            # Check if it's a header that should be sanitized
            elif sanitized_key in cls.SENSITIVE_HEADERS:
                sanitized[key] = cls._mask_value(value)
            # Recursively sanitize nested structures
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value, max_depth - 1)
            elif isinstance(value, list):
                sanitized[key] = cls.sanitize_list(value, max_depth - 1)
            elif isinstance(value, str):
                sanitized[key] = cls.sanitize_string(value)
            else:
                sanitized[key] = value
                
        return sanitized
    
    @classmethod
    def sanitize_list(cls, data: List[Any], max_depth: int = 5) -> List[Any]:
        """Sanitize sensitive data from a list."""
        if max_depth <= 0:
            return ["max_depth_reached"]
            
        if not isinstance(data, list):
            return data
            
        sanitized = []
        
        for item in data:
            if isinstance(item, dict):
                sanitized.append(cls.sanitize_dict(item, max_depth - 1))
            elif isinstance(item, list):
                sanitized.append(cls.sanitize_list(item, max_depth - 1))
            elif isinstance(item, str):
                sanitized.append(cls.sanitize_string(item))
            else:
                sanitized.append(item)
                
        return sanitized
    
    @classmethod
    def sanitize_query_params(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize query parameters."""
        return cls.sanitize_dict(params)
    
    @classmethod
    def sanitize_headers(cls, headers: Dict[str, str]) -> Dict[str, str]:
        """Sanitize HTTP headers."""
        sanitized = {}
        
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower in cls.SENSITIVE_HEADERS:
                sanitized[key] = cls._mask_value(value)
            else:
                # Still sanitize the value for patterns
                sanitized[key] = cls.sanitize_string(str(value))
                
        return sanitized
    
    @classmethod
    def sanitize_request_body(cls, body: str, content_type: str = "") -> str:
        """Sanitize request body based on content type."""
        if not body:
            return body
            
        # For JSON bodies, try to parse and sanitize
        if "application/json" in content_type.lower():
            try:
                import json
                data = json.loads(body)
                if isinstance(data, dict):
                    sanitized_data = cls.sanitize_dict(data)
                    return json.dumps(sanitized_data)
                elif isinstance(data, list):
                    sanitized_data = cls.sanitize_list(data)
                    return json.dumps(sanitized_data)
            except (json.JSONDecodeError, ValueError):
                pass
        
        # For form data or other text
        return cls.sanitize_string(body)
    
    @staticmethod
    def _mask_match(match) -> str:
        """Replace a regex match with masked version."""
        full_match = match.group(0)
        if len(match.groups()) >= 2:
            # Preserve the field name/prefix, mask the value
            prefix = match.group(1)
            value = match.group(2)
            masked_value = LoggingSanitizer._mask_value(value)
            return full_match.replace(value, masked_value)
        else:
            # Mask the entire match
            return LoggingSanitizer._mask_value(full_match)
    
    @staticmethod
    def _mask_value(value: Any) -> str:
        """Mask a sensitive value."""
        if not value:
            return str(value)
            
        str_value = str(value)
        if len(str_value) <= 4:
            return "***"
        elif len(str_value) <= 8:
            return str_value[:2] + "***"
        else:
            return str_value[:3] + "***" + str_value[-2:]


def sanitize_log_data(data: Union[str, Dict, List]) -> Union[str, Dict, List]:
    """Convenience function to sanitize any log data."""
    if isinstance(data, str):
        return LoggingSanitizer.sanitize_string(data)
    elif isinstance(data, dict):
        return LoggingSanitizer.sanitize_dict(data)
    elif isinstance(data, list):
        return LoggingSanitizer.sanitize_list(data)
    else:
        return data