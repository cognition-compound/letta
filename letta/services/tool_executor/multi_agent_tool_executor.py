import asyncio
import os
from typing import Any, Dict, List, Optional

from letta.log import get_logger
from letta.schemas.agent import AgentState
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message import AssistantMessage
from letta.schemas.letta_message_content import TextContent
from letta.schemas.message import MessageCreate
from letta.schemas.sandbox_config import SandboxConfig
from letta.schemas.tool import Tool
from letta.schemas.tool_execution_result import ToolExecutionResult
from letta.schemas.user import User
from letta.services.tool_executor.tool_executor_base import ToolExecutor

logger = get_logger(__name__)


class LettaMultiAgentToolExecutor(ToolExecutor):
    """Executor for LETTA multi-agent core tools."""

    async def execute(
        self,
        function_name: str,
        function_args: dict,
        tool: Tool,
        actor: User,
        agent_state: Optional[AgentState] = None,
        sandbox_config: Optional[SandboxConfig] = None,
        sandbox_env_vars: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        assert agent_state is not None, "Agent state is required for multi-agent tools"
        function_map = {
            "send_message_to_agent_async": self.send_message_to_agent_async,
            "send_message_to_agents_matching_tags": self.send_message_to_agents_matching_tags_async,
            "send": self.send,
        }

        if function_name not in function_map:
            raise ValueError(f"Unknown function: {function_name}")

        # Execute the appropriate function
        function_args_copy = function_args.copy()  # Make a copy to avoid modifying the original
        function_response = await function_map[function_name](agent_state, **function_args_copy)
        return ToolExecutionResult(
            status="success",
            func_return=function_response,
        )

    async def send_message_to_agents_matching_tags_async(
        self, agent_state: AgentState, message: str, match_all: List[str], match_some: List[str]
    ) -> str:
        # Find matching agents
        matching_agents = await self.agent_manager.list_agents_matching_tags_async(
            actor=self.actor, match_all=match_all, match_some=match_some
        )
        if not matching_agents:
            return str([])

        augmented_message = f"[Broadcast message from agent '{agent_state.id}'] {message}"

        tasks = [
            asyncio.create_task(self._process_agent(agent_id=agent_state.id, message=augmented_message)) for agent_state in matching_agents
        ]
        results = await asyncio.gather(*tasks)
        return str(results)

    async def _process_agent(self, agent_id: str, message: str) -> Dict[str, Any]:
        from letta.agents.letta_agent import LettaAgent
        
        # Log and validate agent_id
        logger.debug(f"_process_agent called with agent_id={agent_id!r} (type: {type(agent_id).__name__})")
        
        # Defensive check
        if isinstance(agent_id, list):
            logger.warning(f"agent_id was passed as a list {agent_id}, extracting first element")
            if len(agent_id) == 0:
                raise ValueError("agent_id list is empty")
            agent_id = agent_id[0]

        try:
            letta_agent = LettaAgent(
                agent_id=agent_id,
                message_manager=self.message_manager,
                agent_manager=self.agent_manager,
                block_manager=self.block_manager,
                job_manager=self.job_manager,
                passage_manager=self.passage_manager,
                actor=self.actor,
            )

            letta_response = await letta_agent.step([MessageCreate(role=MessageRole.system, content=[TextContent(text=message)])])
            messages = letta_response.messages

            send_message_content = [message.content for message in messages if isinstance(message, AssistantMessage)]

            return {
                "agent_id": agent_id,
                "response": send_message_content if send_message_content else ["<no response>"],
            }

        except Exception as e:
            return {
                "agent_id": agent_id,
                "error": str(e),
                "type": type(e).__name__,
            }

    async def send_message_to_agent_async(self, agent_state: AgentState, message: str, other_agent_id: str) -> str:
        """Send message to agent without waiting for response."""
        
        # Log the agent_id being used for debugging
        logger.debug(f"send_message_to_agent_async called with other_agent_id={other_agent_id!r} (type: {type(other_agent_id).__name__})")
        
        # Defensive check: ensure other_agent_id is a string
        if isinstance(other_agent_id, list):
            logger.warning(f"other_agent_id was passed as a list {other_agent_id}, extracting first element")
            if len(other_agent_id) == 0:
                raise ValueError("other_agent_id list is empty")
            other_agent_id = other_agent_id[0]

        # Build the prefixed system message
        prefixed = f"[Message from agent '{agent_state.id}'] {message}"

        task = asyncio.create_task(self._process_agent(agent_id=other_agent_id, message=prefixed))

        task.add_done_callback(lambda t: (logger.error(f"Async send_message task failed: {t.exception()}") if t.exception() else None))

        return "Successfully sent message"

    async def send(self, agent_state: AgentState, message: str, to: str) -> str:
        """Universal message sending function with explicit routing."""
        if to == "user":
            # For user messages, just return the success message
            # The actual message delivery is handled by the streaming interfaces
            # which look for the tool name and extract the message parameter
            return "Message sent to user"

        elif to.startswith("agent:"):
            agent_id = to.split(":", 1)[1]
            return await self.send_message_to_agent_async(agent_state, message, agent_id)

        elif to.startswith("group:"):
            # TODO: Implement group messaging in executor
            return "Message sent to group"

        elif to.startswith("broadcast:"):
            tag = to.split(":", 1)[1]
            result = await self.send_message_to_agents_matching_tags_async(agent_state, message, match_all=[tag], match_some=[])
            # Parse the result to get count
            try:
                results = eval(result)  # Safe since we control the format
                return f"Message broadcasted to {len(results)} agents with tag '{tag}'"
            except:
                return f"Message broadcasted to agents with tag '{tag}'"

        else:
            raise ValueError(f"Invalid 'to' parameter: {to}. Must be 'user', 'agent:<id>', 'group:<id>', or 'broadcast:<tag>'")
