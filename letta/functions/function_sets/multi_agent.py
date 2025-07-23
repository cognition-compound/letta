import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, List

from letta.functions.helpers import (
    _send_message_to_all_agents_in_group_async,
    extract_send_message_from_steps_messages,
    fire_and_forget_send_to_agent,
)
from letta.schemas.enums import MessageRole
from letta.schemas.message import MessageCreate
from letta.server.rest_api.utils import get_letta_server
from letta.settings import settings

if TYPE_CHECKING:
    from letta.agent import Agent


def send_message_to_agents_matching_tags(self: "Agent", message: str, match_all: List[str], match_some: List[str]) -> List[str]:
    """
    Sends a message to all agents within the same organization that match the specified tag criteria. Agents must possess *all* of the tags in `match_all` and *at least one* of the tags in `match_some` to receive the message.

    Args:
        message (str): The content of the message to be sent to each matching agent.
        match_all (List[str]): A list of tags that an agent must possess to receive the message.
        match_some (List[str]): A list of tags where an agent must have at least one to qualify.

    Returns:
        List[str]: A list of responses from the agents that matched the filtering criteria. Each
        response corresponds to a single agent. Agents that do not respond will not have an entry
        in the returned list.
    """
    server = get_letta_server()

    # Find matching agents
    matching_agents = server.agent_manager.list_agents_matching_tags(actor=self.user, match_all=match_all, match_some=match_some)
    if not matching_agents:
        return []

    def process_agent(agent_id: str) -> str:
        """Loads an agent, formats the message, and executes .step()"""
        actor = self.user  # Ensure correct actor context
        agent = server.load_agent(agent_id=agent_id, interface=None, actor=actor)

        # Prepare clean messages with sender context
        messages = [
            MessageCreate(role=MessageRole.system, content=f'[Message from: Agent "{self.agent_state.name}" (ID: {self.agent_state.id})]'),
            MessageCreate(role=MessageRole.user, content=message, name=self.agent_state.name, sender_id=self.agent_state.id),
        ]

        # Run .step() and return the response
        usage_stats = agent.step(
            input_messages=messages,
            chaining=True,
            max_chaining_steps=None,
            stream=False,
            skip_verify=True,
            metadata=None,
            put_inner_thoughts_first=True,
        )

        send_messages = extract_send_message_from_steps_messages(usage_stats.steps_messages, logger=agent.logger)
        response_data = {
            "agent_id": agent_id,
            "response_messages": send_messages if send_messages else ["<no response>"],
        }

        return json.dumps(response_data, indent=2)

    # Use ThreadPoolExecutor for parallel execution
    results = []
    with ThreadPoolExecutor(max_workers=settings.multi_agent_concurrent_sends) as executor:
        future_to_agent = {executor.submit(process_agent, agent_state.id): agent_state for agent_state in matching_agents}

        for future in as_completed(future_to_agent):
            try:
                results.append(future.result())  # Collect results
            except Exception as e:
                # Log or handle failure for specific agents if needed
                self.logger.exception(f"Error processing agent {future_to_agent[future]}: {e}")

    return results


def send_message_to_all_agents_in_group(self: "Agent", message: str) -> List[str]:
    """
    Sends a message to all agents within the same multi-agent group.

    Args:
        message (str): The content of the message to be sent to each matching agent.

    Returns:
        List[str]: A list of responses from the agents that matched the filtering criteria. Each
        response corresponds to a single agent. Agents that do not respond will not have an entry
        in the returned list.
    """

    return asyncio.run(_send_message_to_all_agents_in_group_async(self, message))


def send_message_to_agent_async(self: "Agent", message: str, other_agent_id: str) -> str:
    """
    Sends a message to a specific Letta agent within the same organization without waiting for a response. The sender's identity is automatically included in a clean system message. This function is designed for one-way notifications or fire-and-forget messaging.

    Args:
        message (str): The content of the message to be sent to the target agent.
        other_agent_id (str): The unique identifier of the target Letta agent.

    Returns:
        str: A confirmation message indicating the message was successfully sent.
    """
    if os.getenv("LETTA_ENVIRONMENT") == "PRODUCTION":
        raise RuntimeError("This tool is not allowed to be run on Letta Cloud.")

    # Defensive check: ensure other_agent_id is a string
    if isinstance(other_agent_id, list):
        self.logger.warning(f"other_agent_id was passed as a list {other_agent_id}, extracting first element")
        if len(other_agent_id) == 0:
            raise ValueError("other_agent_id list is empty")
        other_agent_id = other_agent_id[0]

    # Create clean messages with sender context in system message
    messages = [
        MessageCreate(role=MessageRole.system, content=f'[Message from: Agent "{self.agent_state.name}" (ID: {self.agent_state.id})]'),
        MessageCreate(role=MessageRole.user, content=message, name=self.agent_state.name, sender_id=self.agent_state.id),
    ]

    # Use fire-and-forget to send without waiting
    fire_and_forget_send_to_agent(
        sender_agent=self,
        messages=messages,
        other_agent_id=other_agent_id,
        log_prefix="[send_message_to_agent_async]",
        use_retries=False,
    )

    return "Message sent successfully"


def send(self: "Agent", message: str, to: str) -> str:
    """
    Universal message sending function with explicit routing. Provides a unified interface for all messaging needs.

    Args:
        message (str): The content of the message to send.
        to (str): Target specification:
            - "user" - sends to the human user
            - "agent:<agent_id>" - sends to a specific agent
            - "group:<group_id>" - sends to all agents in a group
            - "broadcast:<tag>" - sends to all agents with the specified tag

    Returns:
        str: Confirmation message indicating the message was sent.

    Examples:
        - send("Hello!", to="user") - Send to human user
        - send("Status update", to="agent:agent-123") - Async message to agent
        - send("Alert", to="broadcast:critical") - Broadcast to all agents with 'critical' tag
    """
    if to == "user":
        # Import here to avoid circular dependencies
        from letta.functions.function_sets.base import send_message

        send_message(self, message)
        return "Message sent to user"

    elif to.startswith("agent:"):
        agent_id = to.split(":", 1)[1]
        # Check if the agent_id is a UUID without the "agent-" prefix
        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', agent_id, re.IGNORECASE):
            # If it's a UUID, prepend "agent-" since Letta expects "agent-<uuid>" format
            agent_id = f"agent-{agent_id}"
        return send_message_to_agent_async(self, message, agent_id)

    elif to.startswith("group:"):
        group_id = to.split(":", 1)[1]
        # Note: send_message_to_all_agents_in_group doesn't use group_id parameter
        # It sends to all agents in the sender's group
        responses = send_message_to_all_agents_in_group(self, message)
        return f"Message sent to {len(responses)} agents in group"

    elif to.startswith("broadcast:"):
        tag = to.split(":", 1)[1]
        responses = send_message_to_agents_matching_tags(self, message, match_all=[tag], match_some=[])
        return f"Message broadcasted to {len(responses)} agents with tag '{tag}'"

    elif re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", to, re.IGNORECASE):
        # Looks like a UUID, prepend "agent-" and treat as agent ID
        agent_id = f"agent-{to}"
        return send_message_to_agent_async(self, message, agent_id)

    else:
        raise ValueError(
            f"Invalid 'to' parameter: {to}. Must be 'user', 'agent:<id>', 'group:<id>', 'broadcast:<tag>', or a UUID (which will be auto-prefixed with 'agent-')"
        )
