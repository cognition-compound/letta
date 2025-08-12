import asyncio
import json
import traceback
from typing import List, Optional, Tuple, Union

from letta.agents.ephemeral_summary_agent import EphemeralSummaryAgent
from letta.constants import DEFAULT_MESSAGE_TOOL, DEFAULT_MESSAGE_TOOL_KWARG, MESSAGE_SUMMARY_REQUEST_ACK
from letta.helpers.message_helper import convert_message_creates_to_messages
from letta.llm_api.llm_client import LLMClient
from letta.log import get_logger
from letta.otel.tracing import trace_method
from letta.prompts import gpt_summarize
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message, MessageCreate
from letta.schemas.user import User
from letta.services.summarizer.enums import SummarizationMode
from letta.system import package_summarize_message_no_counts
from letta.templates.template_helper import render_template

logger = get_logger(__name__)


class Summarizer:
    """
    Handles summarization or trimming of conversation messages based on
    the specified SummarizationMode. For now, we demonstrate a simple
    static buffer approach but leave room for more advanced strategies.
    """

    def __init__(
        self,
        mode: SummarizationMode,
        summarizer_agent: Optional[Union[EphemeralSummaryAgent, "VoiceSleeptimeAgent"]] = None,
        message_buffer_limit: int = 10,
        message_buffer_min: int = 3,
        partial_evict_summarizer_percentage: float = 0.30,
    ):
        self.mode = mode

        # Need to do validation on this
        # TODO: Move this to config
        self.message_buffer_limit = message_buffer_limit
        self.message_buffer_min = message_buffer_min
        self.summarizer_agent = summarizer_agent
        self.partial_evict_summarizer_percentage = partial_evict_summarizer_percentage

    @trace_method
    async def summarize(
        self,
        in_context_messages: List[Message],
        new_letta_messages: List[Message],
        force: bool = False,
        clear: bool = False,
    ) -> Tuple[List[Message], bool]:
        """
        Summarizes or trims in_context_messages according to the chosen mode,
        and returns the updated messages plus any optional "summary message".

        Args:
            in_context_messages: The existing messages in the conversation's context.
            new_letta_messages: The newly added Letta messages (just appended).
            force: Force summarize even if the criteria is not met

        Returns:
            (updated_messages, summary_message)
            updated_messages: The new context after trimming/summary
            summary_message: Optional summarization message that was created
                             (could be appended to the conversation if desired)
        """
        if self.mode == SummarizationMode.STATIC_MESSAGE_BUFFER:
            return self._static_buffer_summarization(
                in_context_messages,
                new_letta_messages,
                force=force,
                clear=clear,
            )
        elif self.mode == SummarizationMode.PARTIAL_EVICT_MESSAGE_BUFFER:
            return await self._partial_evict_buffer_summarization(
                in_context_messages,
                new_letta_messages,
                force=force,
                clear=clear,
            )
        else:
            # Fallback or future logic
            return in_context_messages, False

    def fire_and_forget(self, coro):
        task = asyncio.create_task(coro)

        def callback(t):
            try:
                t.result()  # This re-raises exceptions from the task
            except Exception:
                logger.error("Background task failed: %s", traceback.format_exc())

        task.add_done_callback(callback)
        return task

    async def _partial_evict_buffer_summarization(
        self,
        in_context_messages: List[Message],
        new_letta_messages: List[Message],
        force: bool = False,
        clear: bool = False,
    ) -> Tuple[List[Message], bool]:
        """Summarization as implemented in the original MemGPT loop, but using message count instead of token count.
        Evict a partial amount of messages, and replace message[1] with a recursive summary.

        Note that this can't be made sync, because we're waiting on the summary to inject it into the context window,
        unlike the version that writes it to a block.

        Unless force is True, don't summarize.
        Ignore clear, we don't use it.
        """
        all_in_context_messages = in_context_messages + new_letta_messages

        if not force:
            logger.debug("Not forcing summarization, returning in-context messages as is.")
            return all_in_context_messages, False

        # Check if summarizer_agent is available, fallback to static buffer if not
        if self.summarizer_agent is None:
            logger.warning(
                "PARTIAL_EVICT_MESSAGE_BUFFER mode requires a summarizer_agent, but none is available. "
                "Falling back to STATIC_MESSAGE_BUFFER mode. This typically happens when no LLM provider is configured."
            )
            return self._static_buffer_summarization(
                in_context_messages,
                new_letta_messages,
                force=force,
                clear=clear,
            )

        # Very ugly code to pull LLMConfig etc from the SummarizerAgent if we're not using it for anything else

        # First step: determine how many messages to retain
        total_message_count = len(all_in_context_messages)
        assert self.partial_evict_summarizer_percentage >= 0.0 and self.partial_evict_summarizer_percentage <= 1.0
        target_message_start = round((1.0 - self.partial_evict_summarizer_percentage) * total_message_count)
        logger.info(f"Target message count: {total_message_count}->{(total_message_count-target_message_start)}")

        # The summary message we'll insert is role 'user' (vs 'assistant', 'tool', or 'system')
        # We are going to put it at index 1 (index 0 is the system message)
        # That means that index 2 needs to be role 'assistant', so walk up the list starting at
        # the target_message_count and find the first assistant message
        for i in range(target_message_start, total_message_count):
            if all_in_context_messages[i].role == MessageRole.assistant:
                assistant_message_index = i
                break
        else:
            raise ValueError(f"No assistant message found from indices {target_message_start} to {total_message_count}")

        # The sequence to summarize is index 1 -> assistant_message_index
        messages_to_summarize = all_in_context_messages[1:assistant_message_index]
        logger.info(f"Eviction indices: {1}->{assistant_message_index}(/{total_message_count})")

        # Dynamically get the LLMConfig from the summarizer agent
        # Pretty cringe code here that we need the agent for this but we don't use it
        agent_state = await self.summarizer_agent.agent_manager.get_agent_by_id_async(
            agent_id=self.summarizer_agent.agent_id, actor=self.summarizer_agent.actor
        )

        # TODO if we do this via the "agent", then we can more easily allow toggling on the memory block version
        summary_message_str = await simple_summary(
            messages=messages_to_summarize,
            llm_config=agent_state.llm_config,
            actor=self.summarizer_agent.actor,
            include_ack=True,
        )

        # TODO add counts back
        # Recall message count
        # num_recall_messages_current = await self.message_manager.size_async(actor=self.actor, agent_id=agent_state.id)
        # num_messages_evicted = len(messages_to_summarize)
        # num_recall_messages_hidden = num_recall_messages_total - len()

        # Create the summary message
        summary_message_str_packed = package_summarize_message_no_counts(
            summary=summary_message_str,
            timezone=agent_state.timezone,
        )
        summary_message_obj = convert_message_creates_to_messages(
            message_creates=[
                MessageCreate(
                    role=MessageRole.user,
                    content=[TextContent(text=summary_message_str_packed)],
                )
            ],
            agent_id=agent_state.id,
            timezone=agent_state.timezone,
            # We already packed, don't pack again
            wrap_user_message=False,
            wrap_system_message=False,
        )[0]

        # Create the message in the DB
        await self.summarizer_agent.message_manager.create_many_messages_async(
            pydantic_msgs=[summary_message_obj],
            actor=self.summarizer_agent.actor,
        )

        updated_in_context_messages = all_in_context_messages[assistant_message_index:]
        return [all_in_context_messages[0], summary_message_obj] + updated_in_context_messages, True

    def _static_buffer_summarization(
        self,
        in_context_messages: List[Message],
        new_letta_messages: List[Message],
        force: bool = False,
        clear: bool = False,
    ) -> Tuple[List[Message], bool]:
        """
        Implements static buffer summarization by maintaining a fixed-size message buffer (< N messages).

        Logic:
        1. Combine existing context messages with new messages
        2. If total messages <= buffer limit and not forced, return unchanged
        3. Calculate how many messages to retain (0 if clear=True, otherwise message_buffer_min)
        4. Find the trim index to keep the most recent messages while preserving user message boundaries
        5. Evict older messages (everything between system message and trim index)
        6. If summarizer agent is available, trigger background summarization of evicted messages
        7. Return updated context with system message + retained recent messages

        Args:
            in_context_messages: Existing conversation context messages
            new_letta_messages: Newly added messages to append
            force: Force summarization even if buffer limit not exceeded
            clear: Clear all messages except system message (retain_count = 0)

        Returns:
            Tuple of (updated_messages, was_summarized)
            - updated_messages: New context after trimming/summarization
            - was_summarized: True if messages were evicted and summarization triggered
        """

        all_in_context_messages = in_context_messages + new_letta_messages

        if len(all_in_context_messages) <= self.message_buffer_limit and not force:
            logger.info(
                f"Nothing to evict, returning in context messages as is. Current buffer length is {len(all_in_context_messages)}, limit is {self.message_buffer_limit}."
            )
            return all_in_context_messages, False

        # Always retain at least 2 messages for context continuity, even when clearing
        retain_count = 2 if clear else self.message_buffer_min

        if not force:
            logger.info(f"Buffer length hit {self.message_buffer_limit}, evicting until we retain only {retain_count} messages.")
        else:
            logger.info(f"Requested force summarization, evicting until we retain only {retain_count} messages.")

        target_trim_index = max(1, len(all_in_context_messages) - retain_count)
        
        # CRITICAL FIX: Prevent trim index from going past message bounds
        if target_trim_index >= len(all_in_context_messages):
            target_trim_index = max(1, len(all_in_context_messages) - max(2, retain_count // 2))
            logger.warning(f"Trim index would exceed message bounds, adjusted to {target_trim_index}")

        # Try to find a user message boundary, but with limits to prevent runaway search
        original_trim_index = target_trim_index
        max_search_distance = min(10, len(all_in_context_messages) - target_trim_index)
        search_count = 0
        
        while (target_trim_index < len(all_in_context_messages) and 
               all_in_context_messages[target_trim_index].role != MessageRole.user and
               search_count < max_search_distance):
            target_trim_index += 1
            search_count += 1
        
        # If we couldn't find a user message boundary within reasonable distance
        if target_trim_index >= len(all_in_context_messages) or search_count >= max_search_distance:
            logger.warning(f"No user message boundary found within {max_search_distance} messages")
            # Fall back to the original position to preserve some context
            target_trim_index = min(original_trim_index, len(all_in_context_messages) - 2)

        # CRITICAL FIX: Ensure tool call/response pairs are preserved as atomic units
        # Check if the trim boundary would split a tool call from its response
        target_trim_index = self._adjust_trim_index_for_tool_pairs(all_in_context_messages, target_trim_index)

        # Final safety check after tool pair adjustment
        if target_trim_index >= len(all_in_context_messages) - 1:
            # We would trim almost everything - keep at least some context
            target_trim_index = max(1, len(all_in_context_messages) - max(retain_count, 5))
            logger.warning(f"Trim would remove too much context, keeping last {len(all_in_context_messages) - target_trim_index} messages")

        evicted_messages = all_in_context_messages[1:target_trim_index]  # everything except sys msg
        updated_in_context_messages = all_in_context_messages[target_trim_index:]  # may be empty
        
        # CRITICAL: Never return empty context (system message only)
        if len(updated_in_context_messages) == 0:
            logger.error("Summarization would leave no context! Keeping minimal context.")
            # Keep at least the last few messages
            keep_last = min(max(retain_count, 5), len(all_in_context_messages) - 1)
            updated_in_context_messages = all_in_context_messages[-keep_last:] if keep_last > 0 else all_in_context_messages[-2:]
            evicted_messages = all_in_context_messages[1:-len(updated_in_context_messages)] if len(updated_in_context_messages) > 0 else []

        # If *no* messages were evicted we really have nothing to do
        if not evicted_messages:
            logger.info("Nothing to evict, returning in-context messages as-is.")
            return all_in_context_messages, False

        if self.summarizer_agent:
            # Only invoke if summarizer agent is passed in
            # Format
            formatted_evicted_messages = format_transcript(evicted_messages)
            formatted_in_context_messages = format_transcript(updated_in_context_messages)

            # TODO: This is hyperspecific to voice, generalize!
            # Update the message transcript of the memory agent
            if not isinstance(self.summarizer_agent, EphemeralSummaryAgent):
                self.summarizer_agent.update_message_transcript(
                    message_transcripts=formatted_evicted_messages + formatted_in_context_messages
                )

            # Add line numbers to the formatted messages
            offset = len(formatted_evicted_messages)
            formatted_evicted_messages = [f"{i}. {msg}" for (i, msg) in enumerate(formatted_evicted_messages)]
            formatted_in_context_messages = [f"{i + offset}. {msg}" for (i, msg) in enumerate(formatted_in_context_messages)]

            summary_request_text = render_template(
                "summary_request_text.j2",
                retain_count=retain_count,
                evicted_messages=formatted_evicted_messages,
                in_context_messages=formatted_in_context_messages,
            )

            # Fire-and-forget the summarization task
            self.fire_and_forget(
                self.summarizer_agent.step([MessageCreate(role=MessageRole.user, content=[TextContent(text=summary_request_text)])])
            )

        return [all_in_context_messages[0]] + updated_in_context_messages, True

    def _adjust_trim_index_for_tool_pairs(self, messages: List[Message], target_trim_index: int) -> int:
        """
        Adjust the trim index to ensure tool call/response pairs are not split.
        
        This method scans backwards and forwards from the target trim index to ensure:
        1. No tool responses are preserved while their tool calls are evicted
        2. No tool calls are preserved while their responses are evicted
        
        Args:
            messages: List of all messages in the conversation
            target_trim_index: The initial trim index (where to start keeping messages)
            
        Returns:
            Adjusted trim index that preserves tool call/response integrity
        """
        if target_trim_index >= len(messages):
            return target_trim_index
            
        # Build a map of tool_call_id -> assistant message index for quick lookup
        tool_call_to_assistant = {}
        for i, msg in enumerate(messages):
            if msg.role == MessageRole.assistant and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_call_to_assistant[tool_call.id] = i
        
        # Check messages that would be kept (from target_trim_index onwards)
        # Look for orphaned tool responses that reference evicted tool calls
        orphaned_responses = []
        for i in range(target_trim_index, len(messages)):
            msg = messages[i]
            if msg.role == MessageRole.tool and msg.tool_call_id:
                # This tool response would be kept - check if its tool call would be evicted
                assistant_index = tool_call_to_assistant.get(msg.tool_call_id)
                if assistant_index is not None and assistant_index < target_trim_index:
                    # Tool call would be evicted but response would be kept - orphaned response!
                    orphaned_responses.append((i, msg.tool_call_id, assistant_index))
        
        if orphaned_responses:
            logger.info(f"Found {len(orphaned_responses)} orphaned tool responses that would be kept while their tool calls are evicted")
            
            # Strategy: Move the trim index backwards to include the tool calls
            # Find the earliest assistant message that needs to be preserved
            earliest_assistant_to_keep = min(assistant_idx for _, _, assistant_idx in orphaned_responses)
            
            # Adjust trim index to include this assistant message and everything after
            adjusted_trim_index = earliest_assistant_to_keep
            
            # Make sure we still respect the user message boundary requirement
            # Walk backwards from the earliest assistant to find a user message boundary
            while adjusted_trim_index > 1 and messages[adjusted_trim_index].role != MessageRole.user:
                adjusted_trim_index -= 1
                
            logger.info(f"Adjusted trim index from {target_trim_index} to {adjusted_trim_index} to preserve tool call/response pairs")
            return adjusted_trim_index
        
        # Check messages that would be evicted (from 1 to target_trim_index)
        # Look for tool calls whose responses would be kept
        orphaned_calls = []
        for i in range(1, target_trim_index):
            msg = messages[i]
            if msg.role == MessageRole.assistant and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    # Look for this tool call's response in the kept messages
                    for j in range(target_trim_index, len(messages)):
                        response_msg = messages[j]
                        if (response_msg.role == MessageRole.tool and 
                            response_msg.tool_call_id == tool_call.id):
                            # Tool call would be evicted but response would be kept
                            orphaned_calls.append((i, tool_call.id, j))
                            break
        
        if orphaned_calls:
            logger.info(f"Found {len(orphaned_calls)} tool calls that would be evicted while their responses are kept")
            
            # Strategy: Move the trim index forward to exclude the orphaned responses
            # Find the latest response message that needs to be excluded
            latest_response_to_exclude = max(response_idx for _, _, response_idx in orphaned_calls)
            
            # Adjust trim index to exclude this response and everything before it
            adjusted_trim_index = latest_response_to_exclude + 1
            
            # Make sure we still have something to keep and respect user message boundaries
            while adjusted_trim_index < len(messages) and messages[adjusted_trim_index].role != MessageRole.user:
                adjusted_trim_index += 1
                
            # Don't go beyond the end of messages
            if adjusted_trim_index >= len(messages):
                logger.warning("Trim adjustment would exclude all messages - keeping original trim index")
                return target_trim_index
                
            logger.info(f"Adjusted trim index from {target_trim_index} to {adjusted_trim_index} to exclude orphaned tool responses")
            return adjusted_trim_index
            
        # No adjustments needed
        return target_trim_index


def simple_formatter(messages: List[Message], include_system: bool = False) -> str:
    """Go from an OpenAI-style list of messages to a concatenated string"""

    parsed_messages = [message.to_openai_dict() for message in messages if message.role != MessageRole.system or include_system]
    return "\n".join(json.dumps(msg) for msg in parsed_messages)


def simple_message_wrapper(openai_msg: dict) -> Message:
    """Extremely simple way to map from role/content to Message object w/ throwaway dummy fields"""

    if "role" not in openai_msg:
        raise ValueError(f"Missing role in openai_msg: {openai_msg}")
    if "content" not in openai_msg:
        raise ValueError(f"Missing content in openai_msg: {openai_msg}")

    if openai_msg["role"] == "user":
        return Message(
            role=MessageRole.user,
            content=[TextContent(text=openai_msg["content"])],
        )
    elif openai_msg["role"] == "assistant":
        return Message(
            role=MessageRole.assistant,
            content=[TextContent(text=openai_msg["content"])],
        )
    elif openai_msg["role"] == "system":
        return Message(
            role=MessageRole.system,
            content=[TextContent(text=openai_msg["content"])],
        )
    else:
        raise ValueError(f"Unknown role: {openai_msg['role']}")


async def simple_summary(messages: List[Message], llm_config: LLMConfig, actor: User, include_ack: bool = True) -> str:
    """Generate a simple summary from a list of messages.

    Intentionally kept functional due to the simplicity of the prompt.
    """

    # Create an LLMClient from the config
    llm_client = LLMClient.create(
        provider_type=llm_config.model_endpoint_type,
        put_inner_thoughts_first=True,
        actor=actor,
    )
    assert llm_client is not None

    # Prepare the messages payload to send to the LLM
    system_prompt = gpt_summarize.SYSTEM
    summary_transcript = simple_formatter(messages)

    if include_ack:
        input_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": MESSAGE_SUMMARY_REQUEST_ACK},
            {"role": "user", "content": summary_transcript},
        ]
    else:
        input_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": summary_transcript},
        ]
    input_messages_obj = [simple_message_wrapper(msg) for msg in input_messages]

    request_data = llm_client.build_request_data(input_messages_obj, llm_config, tools=[])
    # NOTE: we should disable the inner_thoughts_in_kwargs here, because we don't use it
    # I'm leaving it commented it out for now for safety but is fine assuming the var here is a copy not a reference
    # llm_config.put_inner_thoughts_in_kwargs = False
    response_data = await llm_client.request_async(request_data, llm_config)
    response = llm_client.convert_response_to_chat_completion(response_data, input_messages_obj, llm_config)
    if response.choices[0].message.content is None:
        logger.warning("No content returned from summarizer")
        # TODO raise an error error instead?
        # return "[Summary failed to generate]"
        raise Exception("Summary failed to generate")
    else:
        summary = response.choices[0].message.content.strip()

    return summary


def format_transcript(messages: List[Message], include_system: bool = False) -> List[str]:
    """
    Turn a list of Message objects into a human-readable transcript.

    Args:
        messages: List of Message instances, in chronological order.
        include_system: If True, include system-role messages. Defaults to False.

    Returns:
        A single string, e.g.:
          user: Hey, my name is Matt.
          assistant: Hi Matt! It's great to meet you...
          user: What's the weather like? ...
          assistant: The weather in Las Vegas is sunny...
    """
    lines = []
    for msg in messages:
        role = msg.role.value  # e.g. 'user', 'assistant', 'system', 'tool'
        # skip system messages by default
        if role == "system" and not include_system:
            continue

        # 1) Try plain content
        if msg.content:
            # Skip tool messages where the name is "send_message"
            if msg.role == MessageRole.tool and msg.name == DEFAULT_MESSAGE_TOOL:
                continue

            text = "".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()

        # 2) Otherwise, try extracting from function calls
        elif msg.tool_calls:
            parts = []
            for call in msg.tool_calls:
                args_str = call.function.arguments
                if call.function.name == DEFAULT_MESSAGE_TOOL:
                    try:
                        args = json.loads(args_str)
                        # pull out a "message" field if present
                        parts.append(args.get(DEFAULT_MESSAGE_TOOL_KWARG, args_str))
                    except json.JSONDecodeError:
                        parts.append(args_str)
                else:
                    parts.append(args_str)
            text = " ".join(parts).strip()

        else:
            # nothing to show for this message
            continue

        lines.append(f"{role}: {text}")

    return lines
