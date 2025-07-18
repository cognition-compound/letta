"""Test OTEL fixes for None value handling in context attributes and metric recording."""

import pytest
from unittest.mock import patch, Mock, MagicMock
from typing import Dict, Any

from letta.otel.context import (
    request_attributes,
    set_ctx_attributes,
    add_ctx_attribute,
    get_ctx_attributes,
    get_filtered_ctx_attributes
)
from letta.otel.metrics import _safe_add_ctx_attribute


class TestOtelContextFiltering:
    """Test that context attribute filtering works correctly."""
    
    def test_get_filtered_ctx_attributes_removes_none_values(self):
        """Test that get_filtered_ctx_attributes() filters out None values properly."""
        # Reset context
        request_attributes.set({})
        
        # Set attributes with mix of None and non-None values
        test_attrs = {
            "organization.id": "org-123",
            "project.id": None,
            "agent.id": "agent-456",
            "template.id": None,
            "user.id": "user-789",
            "empty_string": "",
            "zero": 0,
            "false": False,
        }
        set_ctx_attributes(test_attrs)
        
        # Get filtered attributes
        filtered = get_filtered_ctx_attributes()
        
        # Assert None values are filtered out
        assert "organization.id" in filtered
        assert "agent.id" in filtered
        assert "user.id" in filtered
        assert "empty_string" in filtered  # Empty string should be kept
        assert "zero" in filtered  # Zero should be kept
        assert "false" in filtered  # False should be kept
        
        # None values should be filtered out
        assert "project.id" not in filtered
        assert "template.id" not in filtered
        
        # Verify values are correct
        assert filtered["organization.id"] == "org-123"
        assert filtered["agent.id"] == "agent-456"
        assert filtered["user.id"] == "user-789"
        assert filtered["empty_string"] == ""
        assert filtered["zero"] == 0
        assert filtered["false"] is False
    
    def test_get_ctx_attributes_returns_all_values(self):
        """Test that get_ctx_attributes() returns all values including None."""
        # Reset context
        request_attributes.set({})
        
        # Set attributes with None values
        test_attrs = {
            "organization.id": "org-123",
            "project.id": None,
            "agent.id": "agent-456",
        }
        set_ctx_attributes(test_attrs)
        
        # Get all attributes (unfiltered)
        all_attrs = get_ctx_attributes()
        
        # All values should be present
        assert len(all_attrs) == 3
        assert all_attrs["organization.id"] == "org-123"
        assert all_attrs["project.id"] is None
        assert all_attrs["agent.id"] == "agent-456"
    
    def test_add_ctx_attribute_with_none(self):
        """Test adding individual attributes including None values."""
        # Reset context
        request_attributes.set({})
        
        # Add attributes one by one
        add_ctx_attribute("key1", "value1")
        add_ctx_attribute("key2", None)
        add_ctx_attribute("key3", "value3")
        
        # Check unfiltered
        all_attrs = get_ctx_attributes()
        assert len(all_attrs) == 3
        assert all_attrs["key1"] == "value1"
        assert all_attrs["key2"] is None
        assert all_attrs["key3"] == "value3"
        
        # Check filtered
        filtered = get_filtered_ctx_attributes()
        assert len(filtered) == 2
        assert filtered["key1"] == "value1"
        assert filtered["key3"] == "value3"
        assert "key2" not in filtered


class TestSafeAddCtxAttribute:
    """Test the _safe_add_ctx_attribute function."""
    
    @patch('letta.otel.metrics.add_ctx_attribute')
    def test_safe_add_ctx_attribute_filters_none(self, mock_add_ctx):
        """Test that _safe_add_ctx_attribute filters out None values."""
        _safe_add_ctx_attribute("test_key", None)
        
        # Should not call add_ctx_attribute for None values
        mock_add_ctx.assert_not_called()
    
    @patch('letta.otel.metrics.add_ctx_attribute')
    def test_safe_add_ctx_attribute_converts_non_primitives(self, mock_add_ctx):
        """Test that _safe_add_ctx_attribute converts non-primitive types to strings."""
        # Test with a complex object
        class CustomObject:
            def __str__(self):
                return "custom_object_string"
        
        obj = CustomObject()
        _safe_add_ctx_attribute("test_key", obj)
        
        # Should convert to string
        mock_add_ctx.assert_called_once_with("test_key", "custom_object_string")
    
    @patch('letta.otel.metrics.add_ctx_attribute')
    def test_safe_add_ctx_attribute_filters_empty_strings(self, mock_add_ctx):
        """Test that _safe_add_ctx_attribute filters out empty strings."""
        _safe_add_ctx_attribute("test_key", "")
        
        # Should not add empty strings
        mock_add_ctx.assert_not_called()
    
    @patch('letta.otel.metrics.add_ctx_attribute')
    def test_safe_add_ctx_attribute_filters_none_strings(self, mock_add_ctx):
        """Test that _safe_add_ctx_attribute filters out 'None' strings."""
        _safe_add_ctx_attribute("test_key", "None")
        
        # Should not add "None" strings
        mock_add_ctx.assert_not_called()
    
    @patch('letta.otel.metrics.add_ctx_attribute')
    def test_safe_add_ctx_attribute_accepts_valid_primitives(self, mock_add_ctx):
        """Test that _safe_add_ctx_attribute accepts valid primitive types."""
        # Test string
        _safe_add_ctx_attribute("str_key", "valid_string")
        mock_add_ctx.assert_called_with("str_key", "valid_string")
        
        # Test int
        mock_add_ctx.reset_mock()
        _safe_add_ctx_attribute("int_key", 42)
        mock_add_ctx.assert_called_with("int_key", 42)
        
        # Test float
        mock_add_ctx.reset_mock()
        _safe_add_ctx_attribute("float_key", 3.14)
        mock_add_ctx.assert_called_with("float_key", 3.14)
        
        # Test bool
        mock_add_ctx.reset_mock()
        _safe_add_ctx_attribute("bool_key", True)
        mock_add_ctx.assert_called_with("bool_key", True)
    
    @patch('letta.otel.metrics.add_ctx_attribute')
    def test_safe_add_ctx_attribute_handles_zero_and_false(self, mock_add_ctx):
        """Test that _safe_add_ctx_attribute correctly handles zero and False values."""
        # Zero should be added
        _safe_add_ctx_attribute("zero_key", 0)
        mock_add_ctx.assert_called_with("zero_key", 0)
        
        # False should be added
        mock_add_ctx.reset_mock()
        _safe_add_ctx_attribute("false_key", False)
        mock_add_ctx.assert_called_with("false_key", False)


class TestMetricRecordingWithFilteredAttributes:
    """Test that metric recording doesn't throw warnings for None values."""
    
    @patch('letta.otel.metric_registry.MetricRegistry')
    def test_metric_recording_with_none_attributes(self, mock_registry):
        """Test that metric recording handles None values in attributes without warnings."""
        from letta.otel.metrics import _record_endpoint_metrics
        
        # Mock the metric registry
        mock_histogram = MagicMock()
        mock_counter = MagicMock()
        mock_registry_instance = MagicMock()
        mock_registry_instance.endpoint_e2e_ms_histogram = mock_histogram
        mock_registry_instance.endpoint_request_counter = mock_counter
        mock_registry.return_value = mock_registry_instance
        
        # Set up context with None values
        request_attributes.set({})
        set_ctx_attributes({
            "organization.id": "org-123",
            "project.id": None,  # This should be filtered out
            "agent.id": "agent-456",
            "template.id": None,  # This should be filtered out
        })
        
        # Create mock request
        mock_request = Mock()
        mock_request.method = "POST"
        mock_route = Mock()
        mock_route.path = "/v1/test/endpoint"
        mock_request.scope = {"route": mock_route}
        
        # Record metrics
        _record_endpoint_metrics(
            request=mock_request,
            latency_ms=100.5,
            status_code=200
        )
        
        # Verify histogram was called with filtered attributes
        expected_attrs = {
            "endpoint_path": "/v1/test/endpoint",
            "method": "POST",
            "status_code": 200,
            "organization.id": "org-123",
            "agent.id": "agent-456",
            # project.id and template.id should NOT be included
        }
        
        mock_histogram.record.assert_called_once()
        actual_attrs = mock_histogram.record.call_args[1]["attributes"]
        
        # Verify None values were filtered out
        assert "project.id" not in actual_attrs
        assert "template.id" not in actual_attrs
        assert actual_attrs["organization.id"] == "org-123"
        assert actual_attrs["agent.id"] == "agent-456"
        
        # Verify counter was also called correctly
        mock_counter.add.assert_called_once_with(1, attributes=actual_attrs)
    
    @patch('letta.otel.metric_registry.MetricRegistry')
    @patch('letta.log.get_logger')
    def test_metric_recording_no_warnings_for_none(self, mock_get_logger, mock_registry):
        """Test that metric recording doesn't log warnings for None values."""
        from letta.otel.metrics import _record_endpoint_metrics
        
        # Mock logger
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        # Mock the metric registry
        mock_histogram = MagicMock()
        mock_counter = MagicMock()
        mock_registry_instance = MagicMock()
        mock_registry_instance.endpoint_e2e_ms_histogram = mock_histogram
        mock_registry_instance.endpoint_request_counter = mock_counter
        mock_registry.return_value = mock_registry_instance
        
        # Set up context with None values
        request_attributes.set({})
        set_ctx_attributes({
            "organization.id": None,
            "project.id": None,
            "agent.id": None,
        })
        
        # Create mock request
        mock_request = Mock()
        mock_request.method = "GET"
        mock_route = Mock()
        mock_route.path = "/v1/health"
        mock_request.scope = {"route": mock_route}
        
        # Record metrics
        _record_endpoint_metrics(
            request=mock_request,
            latency_ms=50.0,
            status_code=200
        )
        
        # Verify no warnings were logged
        mock_logger.warning.assert_not_called()
        
        # Verify metrics were recorded successfully
        mock_histogram.record.assert_called_once()
        mock_counter.add.assert_called_once()


class TestContextIsolation:
    """Test that context attributes are properly isolated between operations."""
    
    def test_context_isolation_between_requests(self):
        """Test that context attributes don't leak between different operations."""
        # First operation
        request_attributes.set({})
        set_ctx_attributes({"request_id": "req-1", "user_id": "user-1"})
        
        ctx1 = get_filtered_ctx_attributes()
        assert ctx1["request_id"] == "req-1"
        assert ctx1["user_id"] == "user-1"
        
        # Second operation (simulating new request)
        request_attributes.set({})
        set_ctx_attributes({"request_id": "req-2", "org_id": "org-2"})
        
        ctx2 = get_filtered_ctx_attributes()
        assert ctx2["request_id"] == "req-2"
        assert ctx2["org_id"] == "org-2"
        assert "user_id" not in ctx2  # Should not leak from first operation