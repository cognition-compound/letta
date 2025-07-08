from enum import Enum
from typing import Dict, List, Set, Tuple

from pydantic import BaseModel

from letta.schemas.tool import Tool


class ToolSafetyProfile(str, Enum):
    """Classification of tools by their safety profile for parallel execution."""
    
    MEMORY_OPERATION = "memory_operation"  # Tools that modify agent memory state
    EXTERNAL_INTEGRATION = "external_integration"  # Tools that call external APIs/services
    SAFE_PARALLEL = "safe_parallel"  # Tools that are safe to run in parallel
    FILE_OPERATION = "file_operation"  # Tools that perform file I/O operations
    COMMUNICATION = "communication"  # Tools for agent-to-agent communication
    SYSTEM_OPERATION = "system_operation"  # Tools that affect system state


class ToolDependency(BaseModel):
    """Represents a dependency relationship between tools."""
    
    tool_name: str
    depends_on: str
    dependency_type: str  # "data", "ordering", "state"
    description: str


class ToolCategorizationResult(BaseModel):
    """Result of categorizing a set of tools for execution planning."""
    
    memory_tools: List[str]
    safe_parallel_tools: List[str]
    external_tools: List[str]
    file_tools: List[str] 
    communication_tools: List[str]
    system_tools: List[str]
    dependencies: List[ToolDependency]
    recommended_execution_order: List[List[str]]  # Groups of tools that can be executed together


class ToolCategorizer:
    """
    Categorizes tools by safety profile and analyzes dependencies to provide 
    execution recommendations for parallel tool calling.
    """
    
    # Predefined tool classifications based on known Letta tools
    MEMORY_OPERATION_TOOLS = {
        "core_memory_append",
        "core_memory_replace", 
        "archival_memory_insert",
        "archival_memory_search",
        "recall_memory_search",
        "conversation_search",
        "conversation_search_date",
    }
    
    COMMUNICATION_TOOLS = {
        "send_message",
        "send_to_user",
        "send_to_agent",
        "broadcast_message",
        "join_group",
        "leave_group",
    }
    
    FILE_OPERATION_TOOLS = {
        "open_file",
        "search_files", 
        "grep",
        "write_file",
        "create_file",
        "delete_file",
        "list_files",
    }
    
    SYSTEM_OPERATION_TOOLS = {
        "execute_code",
        "run_command",
        "shell_exec",
        "system_call",
    }
    
    # External integration patterns (prefixes/suffixes)
    EXTERNAL_INTEGRATION_PATTERNS = {
        "mcp_",  # MCP tools
        "composio_",  # Composio tools
        "_api",  # API tools
        "_webhook",  # Webhook tools
    }

    def __init__(self):
        # Known dependencies between tools
        self.known_dependencies = [
            ToolDependency(
                tool_name="core_memory_replace",
                depends_on="core_memory_append",
                dependency_type="state",
                description="Memory replace operations may depend on append operations"
            ),
            ToolDependency(
                tool_name="send_message", 
                depends_on="core_memory_append",
                dependency_type="data",
                description="Message content may reference recently added memory"
            ),
        ]

    def categorize_tool(self, tool: Tool) -> ToolSafetyProfile:
        """
        Categorize a single tool by its safety profile.
        
        Args:
            tool: The tool to categorize
            
        Returns:
            ToolSafetyProfile enum indicating the tool's safety category
        """
        tool_name = tool.name.lower() if tool.name else ""
        
        # Check memory operations first (highest priority for safety)
        if tool_name in self.MEMORY_OPERATION_TOOLS:
            return ToolSafetyProfile.MEMORY_OPERATION
            
        # Check communication tools
        if tool_name in self.COMMUNICATION_TOOLS:
            return ToolSafetyProfile.COMMUNICATION
            
        # Check file operations
        if tool_name in self.FILE_OPERATION_TOOLS:
            return ToolSafetyProfile.FILE_OPERATION
            
        # Check system operations
        if tool_name in self.SYSTEM_OPERATION_TOOLS:
            return ToolSafetyProfile.SYSTEM_OPERATION
            
        # Check external integration patterns
        for pattern in self.EXTERNAL_INTEGRATION_PATTERNS:
            if pattern in tool_name:
                return ToolSafetyProfile.EXTERNAL_INTEGRATION
                
        # Default to safe parallel if no specific categorization found
        return ToolSafetyProfile.SAFE_PARALLEL

    def categorize_tools(self, tools: List[Tool]) -> ToolCategorizationResult:
        """
        Categorize a list of tools and analyze their dependencies.
        
        Args:
            tools: List of tools to categorize
            
        Returns:
            ToolCategorizationResult with categorized tools and execution recommendations
        """
        # Categorize each tool
        categorized = {profile: [] for profile in ToolSafetyProfile}
        tool_profiles = {}
        
        for tool in tools:
            profile = self.categorize_tool(tool)
            categorized[profile].append(tool.name)
            tool_profiles[tool.name] = profile
            
        # Analyze dependencies
        relevant_dependencies = self._find_relevant_dependencies([tool.name for tool in tools if tool.name])
        
        # Generate execution order recommendations
        execution_order = self._recommend_execution_order(tool_profiles, relevant_dependencies)
        
        return ToolCategorizationResult(
            memory_tools=categorized[ToolSafetyProfile.MEMORY_OPERATION],
            safe_parallel_tools=categorized[ToolSafetyProfile.SAFE_PARALLEL],
            external_tools=categorized[ToolSafetyProfile.EXTERNAL_INTEGRATION],
            file_tools=categorized[ToolSafetyProfile.FILE_OPERATION],
            communication_tools=categorized[ToolSafetyProfile.COMMUNICATION],
            system_tools=categorized[ToolSafetyProfile.SYSTEM_OPERATION],
            dependencies=relevant_dependencies,
            recommended_execution_order=execution_order,
        )

    def is_safe_for_parallel_execution(
        self, 
        tools: List[Tool], 
        allow_memory_parallel: bool = False,
        allow_file_parallel: bool = True,
        allow_external_parallel: bool = True,
    ) -> Tuple[bool, List[str]]:
        """
        Determine if a set of tools is safe for parallel execution.
        
        Args:
            tools: List of tools to analyze
            allow_memory_parallel: Whether to allow memory tools in parallel
            allow_file_parallel: Whether to allow file tools in parallel  
            allow_external_parallel: Whether to allow external tools in parallel
            
        Returns:
            Tuple of (is_safe, list_of_unsafe_tool_names)
        """
        unsafe_tools = []
        
        for tool in tools:
            profile = self.categorize_tool(tool)
            
            if profile == ToolSafetyProfile.MEMORY_OPERATION and not allow_memory_parallel:
                unsafe_tools.append(tool.name)
            elif profile == ToolSafetyProfile.FILE_OPERATION and not allow_file_parallel:
                unsafe_tools.append(tool.name)
            elif profile == ToolSafetyProfile.EXTERNAL_INTEGRATION and not allow_external_parallel:
                unsafe_tools.append(tool.name)
            elif profile == ToolSafetyProfile.SYSTEM_OPERATION:
                # System operations are generally unsafe for parallel execution
                unsafe_tools.append(tool.name)
                
        return len(unsafe_tools) == 0, unsafe_tools

    def detect_tool_conflicts(self, tools: List[Tool]) -> List[Tuple[str, str, str]]:
        """
        Detect potential conflicts between tools that shouldn't run in parallel.
        
        Args:
            tools: List of tools to analyze
            
        Returns:
            List of tuples (tool1, tool2, conflict_reason)
        """
        conflicts = []
        tool_names = [tool.name for tool in tools]
        
        # Check for memory operation conflicts
        memory_tools = [name for name in tool_names if name in self.MEMORY_OPERATION_TOOLS]
        if len(memory_tools) > 1:
            for i in range(len(memory_tools)):
                for j in range(i + 1, len(memory_tools)):
                    conflicts.append((
                        memory_tools[i], 
                        memory_tools[j], 
                        "Multiple memory operations may cause state conflicts"
                    ))
        
        # Check for file operation conflicts on same files
        # Note: This would require more sophisticated analysis of file paths
        file_tools = [name for name in tool_names if name in self.FILE_OPERATION_TOOLS]
        if len(file_tools) > 1:
            # For now, flag potential conflicts - could be enhanced with file path analysis
            for i in range(len(file_tools)):
                for j in range(i + 1, len(file_tools)):
                    conflicts.append((
                        file_tools[i],
                        file_tools[j], 
                        "File operations may conflict if accessing same files"
                    ))
                    
        return conflicts

    def _find_relevant_dependencies(self, tool_names: List[str]) -> List[ToolDependency]:
        """Find dependencies relevant to the given set of tools."""
        relevant = []
        tool_set = set(tool_names)
        
        for dep in self.known_dependencies:
            if dep.tool_name in tool_set and dep.depends_on in tool_set:
                relevant.append(dep)
                
        return relevant

    def _recommend_execution_order(
        self, 
        tool_profiles: Dict[str, ToolSafetyProfile], 
        dependencies: List[ToolDependency]
    ) -> List[List[str]]:
        """
        Recommend execution order for tools based on dependencies and safety profiles.
        
        Returns a list of groups where each group can be executed in parallel.
        """
        # Start with tools that have no dependencies
        remaining_tools = set(tool_profiles.keys())
        execution_groups = []
        
        # Build dependency graph
        depends_on = {}  # tool -> set of tools it depends on
        for dep in dependencies:
            if dep.tool_name not in depends_on:
                depends_on[dep.tool_name] = set()
            depends_on[dep.tool_name].add(dep.depends_on)
        
        # Process tools in dependency order
        while remaining_tools:
            # Find tools with no remaining dependencies
            ready_tools = []
            for tool in remaining_tools:
                tool_deps = depends_on.get(tool, set())
                if not (tool_deps & remaining_tools):  # No remaining dependencies
                    ready_tools.append(tool)
            
            if not ready_tools:
                # Circular dependency or error - add remaining tools as separate group
                ready_tools = list(remaining_tools)
                
            # Group ready tools by safety profile
            memory_tools = []
            safe_tools = []
            
            for tool in ready_tools:
                if tool_profiles[tool] == ToolSafetyProfile.MEMORY_OPERATION:
                    memory_tools.append(tool)
                else:
                    safe_tools.append(tool)
            
            # Memory tools should be executed separately
            if memory_tools:
                execution_groups.append(memory_tools)
            if safe_tools:
                execution_groups.append(safe_tools)
                
            remaining_tools -= set(ready_tools)
            
        return execution_groups