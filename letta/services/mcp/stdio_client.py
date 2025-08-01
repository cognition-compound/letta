from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from letta.constants import MCP_AGENT_ID_ENV_VAR
from letta.functions.mcp_client.types import StdioServerConfig
from letta.log import get_logger
from letta.services.mcp.base_client import AsyncBaseMCPClient

logger = get_logger(__name__)


# TODO: Get rid of Async prefix on this class name once we deprecate old sync code
class AsyncStdioMCPClient(AsyncBaseMCPClient):
    async def _initialize_connection(self, server_config: StdioServerConfig) -> None:
        args = [arg.split() for arg in server_config.args]
        # flatten
        args = [arg for sublist in args for arg in sublist]
        
        # For stdio transport, pass agent_id as environment variable
        env = server_config.env.copy() if server_config.env else {}
        if self.agent_id:
            env[MCP_AGENT_ID_ENV_VAR] = self.agent_id
        
        server_params = StdioServerParameters(command=server_config.command, args=args, env=env)
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
