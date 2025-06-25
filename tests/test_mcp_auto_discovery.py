import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from letta.functions.mcp_client.types import MCPTool
from letta.orm.enums import ToolType
from letta.schemas.mcp import MCPServer
from letta.schemas.tool import Tool as PydanticTool, ToolCreate
from letta.schemas.user import User as PydanticUser
from letta.services.mcp_manager import MCPManager
from letta.services.tool_manager import ToolManager


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return PydanticUser(
        id="user-12345678",
        name="Test User",
        organization_id="org-87654321"
    )


@pytest.fixture
def mock_mcp_server():
    """Create a mock MCP server for testing."""
    from letta.functions.mcp_client.types import MCPServerType
    return MCPServer(
        id="server-12345678",
        server_name="test-mcp-server",
        server_type=MCPServerType.SSE,
        server_url="https://test.example.com",
        organization_id="org-87654321"
    )


@pytest.fixture
def mock_mcp_tools():
    """Create mock MCP tools for testing."""
    return [
        MCPTool(
            name="test_tool_1",
            description="Test tool 1 description",
            inputSchema={"type": "object", "properties": {"param1": {"type": "string"}}}
        ),
        MCPTool(
            name="test_tool_2", 
            description="Test tool 2 description",
            inputSchema={"type": "object", "properties": {"param2": {"type": "integer"}}}
        ),
        MCPTool(
            name="test_tool_3",
            description="Test tool 3 description", 
            inputSchema={"type": "object", "properties": {"param3": {"type": "boolean"}}}
        )
    ]


@pytest.fixture
def mock_pydantic_tools():
    """Create mock Pydantic tools for testing."""
    return [
        PydanticTool(
            id="tool-1-id",
            name="test_tool_1",
            tool_type=ToolType.EXTERNAL_MCP,
            source_code="def test_tool_1(): pass",
            json_schema={"name": "test_tool_1", "type": "function"}
        ),
        PydanticTool(
            id="tool-2-id", 
            name="test_tool_2",
            tool_type=ToolType.EXTERNAL_MCP,
            source_code="def test_tool_2(): pass",
            json_schema={"name": "test_tool_2", "type": "function"}
        ),
        PydanticTool(
            id="tool-3-id",
            name="test_tool_3", 
            tool_type=ToolType.EXTERNAL_MCP,
            source_code="def test_tool_3(): pass",
            json_schema={"name": "test_tool_3", "type": "function"}
        )
    ]


class TestMCPAutoDiscovery:
    """Test suite for MCP auto-discovery functionality."""

    @pytest.mark.asyncio
    async def test_auto_register_mcp_tools_async_success(self, mock_user, mock_mcp_tools, mock_pydantic_tools):
        """Test successful auto-registration of MCP tools."""
        mcp_manager = MCPManager()
        
        # Mock the list_mcp_server_tools method
        with patch.object(mcp_manager, 'list_mcp_server_tools', new=AsyncMock(return_value=mock_mcp_tools)):
            # Mock the tool manager's create_mcp_tool_async method
            with patch.object(mcp_manager.tool_manager, 'create_mcp_tool_async', new=AsyncMock()) as mock_create_tool:
                # Set up the mock to return the corresponding pydantic tool for each call
                mock_create_tool.side_effect = mock_pydantic_tools
                
                # Execute the auto-registration
                successful_tools, failed_tools = await mcp_manager._auto_register_mcp_tools_async(
                    "test-mcp-server", mock_user
                )
                
                # Verify results
                assert len(successful_tools) == 3
                assert len(failed_tools) == 0
                assert successful_tools == mock_pydantic_tools
                
                # Verify that create_mcp_tool_async was called for each tool
                assert mock_create_tool.call_count == 3
                
                # Verify the calls were made with correct parameters
                for i, call in enumerate(mock_create_tool.call_args_list):
                    args, kwargs = call
                    assert kwargs['mcp_server_name'] == "test-mcp-server"
                    assert kwargs['actor'] == mock_user
                    assert isinstance(kwargs['tool_create'], ToolCreate)

    @pytest.mark.asyncio
    async def test_auto_register_mcp_tools_async_no_tools(self, mock_user):
        """Test auto-registration when MCP server has no tools."""
        mcp_manager = MCPManager()
        
        # Mock the list_mcp_server_tools method to return empty list
        with patch.object(mcp_manager, 'list_mcp_server_tools', new=AsyncMock(return_value=[])):
            successful_tools, failed_tools = await mcp_manager._auto_register_mcp_tools_async(
                "test-mcp-server", mock_user
            )
            
            assert len(successful_tools) == 0
            assert len(failed_tools) == 0

    @pytest.mark.asyncio
    async def test_auto_register_mcp_tools_async_discovery_failure(self, mock_user):
        """Test auto-registration when tool discovery fails."""
        mcp_manager = MCPManager()
        
        # Mock the list_mcp_server_tools method to raise an exception
        with patch.object(mcp_manager, 'list_mcp_server_tools', new=AsyncMock(side_effect=Exception("Connection failed"))):
            successful_tools, failed_tools = await mcp_manager._auto_register_mcp_tools_async(
                "test-mcp-server", mock_user
            )
            
            assert len(successful_tools) == 0
            assert len(failed_tools) == 1
            assert "Failed to discover tools: Connection failed" in failed_tools[0]

    @pytest.mark.asyncio
    async def test_auto_register_mcp_tools_async_partial_failure(self, mock_user, mock_mcp_tools, mock_pydantic_tools):
        """Test auto-registration with partial tool registration failures."""
        mcp_manager = MCPManager()
        
        # Mock the list_mcp_server_tools method
        with patch.object(mcp_manager, 'list_mcp_server_tools', new=AsyncMock(return_value=mock_mcp_tools)):
            # Mock the tool manager's create_mcp_tool_async method to fail for second tool
            with patch.object(mcp_manager.tool_manager, 'create_mcp_tool_async', new=AsyncMock()) as mock_create_tool:
                def side_effect(*args, **kwargs):
                    tool_name = kwargs['tool_create'].json_schema.get('name', 'unknown')
                    if tool_name == 'test_tool_2':
                        raise Exception("Tool registration failed")
                    # Return corresponding tool based on name
                    for tool in mock_pydantic_tools:
                        if tool.name == tool_name:
                            return tool
                    return mock_pydantic_tools[0]  # fallback
                
                mock_create_tool.side_effect = side_effect
                
                successful_tools, failed_tools = await mcp_manager._auto_register_mcp_tools_async(
                    "test-mcp-server", mock_user  
                )
                
                # Should have 2 successful tools and 1 failure
                assert len(successful_tools) == 2
                assert len(failed_tools) == 1
                assert "test_tool_2: Tool registration failed" in failed_tools[0]
                
                # Verify successful tools don't include the failed one
                successful_names = [tool.name for tool in successful_tools]
                assert "test_tool_1" in successful_names
                assert "test_tool_3" in successful_names
                assert "test_tool_2" not in successful_names

    @pytest.mark.asyncio
    async def test_auto_register_mcp_tools_async_tool_create_failure(self, mock_user, mock_mcp_tools):
        """Test auto-registration when ToolCreate.from_mcp fails for some tools."""
        mcp_manager = MCPManager()
        
        # Mock the list_mcp_server_tools method
        with patch.object(mcp_manager, 'list_mcp_server_tools', new=AsyncMock(return_value=mock_mcp_tools)):
            # Mock ToolCreate.from_mcp to fail for the second tool
            with patch('letta.schemas.tool.ToolCreate.from_mcp') as mock_from_mcp:
                def side_effect(mcp_server_name, mcp_tool):
                    if mcp_tool.name == 'test_tool_2':
                        raise Exception("Invalid tool schema")
                    return ToolCreate(
                        name=mcp_tool.name,
                        description=mcp_tool.description,
                        source_code=f"def {mcp_tool.name}(): pass",
                        json_schema={"name": mcp_tool.name, "type": "function"}
                    )
                
                mock_from_mcp.side_effect = side_effect
                
                # Mock tool manager
                with patch.object(mcp_manager.tool_manager, 'create_mcp_tool_async', new=AsyncMock()) as mock_create_tool:
                    mock_create_tool.return_value = PydanticTool(
                        id="test-id",
                        name="test_tool",
                        tool_type=ToolType.EXTERNAL_MCP,
                        source_code="def test_tool(): pass",
                        json_schema={"name": "test_tool", "type": "function"}
                    )
                    
                    successful_tools, failed_tools = await mcp_manager._auto_register_mcp_tools_async(
                        "test-mcp-server", mock_user
                    )
                    
                    # Should only register 2 tools (excluding the one that failed in ToolCreate.from_mcp)
                    assert len(successful_tools) == 2
                    assert len(failed_tools) == 0  # ToolCreate failures are logged but not returned as failed_tools
                    assert mock_create_tool.call_count == 2

    @pytest.mark.asyncio
    async def test_create_mcp_server_with_auto_register_enabled(self, mock_user, mock_mcp_server):
        """Test MCP server creation with auto-registration enabled."""
        mcp_manager = MCPManager()
        
        # Mock database operations
        with patch('letta.services.mcp_manager.db_registry.async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.__aenter__.return_value = mock_session_instance
            
            # Mock the MCPServerModel operations
            with patch('letta.services.mcp_manager.MCPServerModel') as mock_model:
                mock_server_instance = Mock()
                mock_server_instance.server_name = "test-mcp-server"
                mock_server_instance.to_pydantic.return_value = mock_mcp_server
                mock_server_instance.create_async = AsyncMock(return_value=mock_server_instance)
                mock_model.return_value = mock_server_instance
                
                # Mock the auto-registration method
                with patch.object(mcp_manager, '_auto_register_mcp_tools_async', new=AsyncMock()) as mock_auto_register:
                    mock_auto_register.return_value = ([], [])  # successful_tools, failed_tools
                    
                    result = await mcp_manager.create_mcp_server(
                        mock_mcp_server, mock_user, auto_register_tools=True
                    )
                    
                    # Verify server was created
                    assert result == mock_mcp_server
                    
                    # Verify auto-registration was called
                    mock_auto_register.assert_called_once_with("test-mcp-server", mock_user)

    @pytest.mark.asyncio
    async def test_create_mcp_server_with_auto_register_disabled(self, mock_user, mock_mcp_server):
        """Test MCP server creation with auto-registration disabled."""
        mcp_manager = MCPManager()
        
        # Mock database operations
        with patch('letta.services.mcp_manager.db_registry.async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.__aenter__.return_value = mock_session_instance
            
            # Mock the MCPServerModel operations
            with patch('letta.services.mcp_manager.MCPServerModel') as mock_model:
                mock_server_instance = Mock()
                mock_server_instance.to_pydantic.return_value = mock_mcp_server
                mock_server_instance.create_async = AsyncMock(return_value=mock_server_instance)
                mock_model.return_value = mock_server_instance
                
                # Mock the auto-registration method
                with patch.object(mcp_manager, '_auto_register_mcp_tools_async', new=AsyncMock()) as mock_auto_register:
                    result = await mcp_manager.create_mcp_server(
                        mock_mcp_server, mock_user, auto_register_tools=False
                    )
                    
                    # Verify server was created
                    assert result == mock_mcp_server
                    
                    # Verify auto-registration was NOT called
                    mock_auto_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_mcp_server_auto_register_failure_doesnt_break_server_creation(self, mock_user, mock_mcp_server):
        """Test that auto-registration failures don't prevent server creation."""
        mcp_manager = MCPManager()
        
        # Mock database operations
        with patch('letta.services.mcp_manager.db_registry.async_session') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.__aenter__.return_value = mock_session_instance
            
            # Mock the MCPServerModel operations
            with patch('letta.services.mcp_manager.MCPServerModel') as mock_model:
                mock_server_instance = Mock()
                mock_server_instance.server_name = "test-mcp-server"
                mock_server_instance.to_pydantic.return_value = mock_mcp_server
                mock_server_instance.create_async = AsyncMock(return_value=mock_server_instance)
                mock_model.return_value = mock_server_instance
                
                # Mock the auto-registration method to raise an exception
                with patch.object(mcp_manager, '_auto_register_mcp_tools_async', new=AsyncMock()) as mock_auto_register:
                    mock_auto_register.side_effect = Exception("Auto-registration failed")
                    
                    # Should still succeed in creating the server
                    result = await mcp_manager.create_mcp_server(
                        mock_mcp_server, mock_user, auto_register_tools=True
                    )
                    
                    # Verify server was created despite auto-registration failure
                    assert result == mock_mcp_server
                    
                    # Verify auto-registration was attempted
                    mock_auto_register.assert_called_once_with("test-mcp-server", mock_user)

    def test_parallel_execution_performance(self, mock_user, mock_pydantic_tools):
        """Test that parallel execution is faster than sequential execution."""
        mcp_manager = MCPManager()
        
        # Create many mock tools to test parallelism
        many_mcp_tools = [
            MCPTool(
                name=f"test_tool_{i}",
                description=f"Test tool {i} description",
                inputSchema={"type": "object", "properties": {f"param{i}": {"type": "string"}}}
            )
            for i in range(10)
        ]
        
        async def slow_create_tool(*args, **kwargs):
            """Simulate slow tool creation."""
            await asyncio.sleep(0.1)  # 100ms delay
            return mock_pydantic_tools[0]
        
        async def test_execution():
            # Mock the list_mcp_server_tools method
            with patch.object(mcp_manager, 'list_mcp_server_tools', new=AsyncMock(return_value=many_mcp_tools)):
                # Mock the tool manager's create_mcp_tool_async method with delay
                with patch.object(mcp_manager.tool_manager, 'create_mcp_tool_async', new=AsyncMock(side_effect=slow_create_tool)):
                    start_time = asyncio.get_event_loop().time()
                    
                    successful_tools, failed_tools = await mcp_manager._auto_register_mcp_tools_async(
                        "test-mcp-server", mock_user
                    )
                    
                    end_time = asyncio.get_event_loop().time()
                    execution_time = end_time - start_time
                    
                    # Should complete in roughly 0.1 seconds (parallel) rather than 1.0 seconds (sequential)
                    # Allow some buffer for test execution overhead
                    assert execution_time < 0.5, f"Execution took {execution_time}s, expected < 0.5s for parallel execution"
                    assert len(successful_tools) == 10
                    assert len(failed_tools) == 0
        
        # Run the async test
        asyncio.run(test_execution())