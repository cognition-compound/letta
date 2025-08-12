"""
Test that reproduces the EXACT scenario causing research agent death in staging.

The research agent:
1. Receives ONE user message (from main agent via send())
2. NEVER sends to user - only uses tools
3. Makes many archival_memory_insert calls
4. Eventually hits context limit
5. Summarizer triggers with force=True, clear=True
6. Searches for user message boundary - finds NONE after initial message
7. Trim index goes to end of messages
8. Agent left with only system message = DEAD
"""

import pytest
from datetime import datetime
from letta.schemas.message import Message
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.services.summarizer.summarizer import Summarizer
from letta.services.summarizer.enums import SummarizationMode
from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall as OpenAIToolCall
from openai.types.chat.chat_completion_message_function_tool_call import Function as OpenAIFunction
import json


def test_research_agent_death_scenario():
    """Reproduce the exact scenario that kills the research agent."""
    
    messages = []
    
    # System message - research agent instructions
    messages.append(Message(
        id="message-00000000",
        role=MessageRole.system,
        content=[TextContent(text="""You are the Research Agent. 
        CRITICAL: NEVER send messages to user - only use tools.
        Always respond to main agent via send(to='agent:main-agent-id').
        Use archival_memory_insert to store findings.""")],
        agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",  # Research agent ID from logs
        created_at=datetime.now()
    ))
    
    # SINGLE user message from main agent (via send())
    messages.append(Message(
        id="message-00000001", 
        role=MessageRole.user,
        content=[TextContent(text="[Message from agent 'agent-ed6055c1-3c50-4dae-8966-36321a827dc9']\nResearch Spinnen (spiders) - comprehensive analysis needed")],
        agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
        created_at=datetime.now()
    ))
    
    # Now the research agent starts working - ONLY tool calls, NO user messages!
    call_id = 2
    
    # First: Many archival_memory_search calls
    for i in range(5):
        # Assistant with archival_memory_search
        messages.append(Message(
            id=f"message-{call_id:08x}",
            role=MessageRole.assistant,
            content=[TextContent(text="")],  # Empty, just tool call
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_calls=[OpenAIToolCall(
                id=f"call_{call_id}",
                function=OpenAIFunction(
                    name="archival_memory_search",
                    arguments=json.dumps({"query": f"spider research query {i}"})
                ),
                type="function"
            )],
            created_at=datetime.now()
        ))
        call_id += 1
        
        # Tool response
        messages.append(Message(
            id=f"message-{call_id:08x}",
            role=MessageRole.tool,
            content=[TextContent(text=f"No results found for query {i}")],
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_call_id=f"call_{call_id-1}",
            name="archival_memory_search",
            created_at=datetime.now()
        ))
        call_id += 1
    
    # Then: Many tavily_search calls to gather information
    for i in range(10):
        # Assistant with tavily_search
        messages.append(Message(
            id=f"message-{call_id:08x}",
            role=MessageRole.assistant,
            content=[TextContent(text="")],
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_calls=[OpenAIToolCall(
                id=f"call_{call_id}",
                function=OpenAIFunction(
                    name="tavily_search",
                    arguments=json.dumps({
                        "query": f"Spinnen spider species habitat behavior {i}",
                        "max_results": 5
                    })
                ),
                type="function"
            )],
            created_at=datetime.now()
        ))
        call_id += 1
        
        # Tool response with large content
        messages.append(Message(
            id=f"message-{call_id:08x}",
            role=MessageRole.tool,
            content=[TextContent(text="Search results: " + "x" * 2000)],  # Large responses
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_call_id=f"call_{call_id-1}",
            name="tavily_search",
            created_at=datetime.now()
        ))
        call_id += 1
    
    # Then: Many archival_memory_insert calls to store findings
    for i in range(50):  # Lots of inserts!
        # Assistant with archival_memory_insert
        messages.append(Message(
            id=f"message-{call_id:08x}",
            role=MessageRole.assistant,
            content=[TextContent(text="")],
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_calls=[OpenAIToolCall(
                id=f"call_{call_id}",
                function=OpenAIFunction(
                    name="archival_memory_insert",
                    arguments=json.dumps({
                        "content": f"Spider fact {i}: " + "detailed information " * 100
                    })
                ),
                type="function"
            )],
            created_at=datetime.now()
        ))
        call_id += 1
        
        # Tool response
        messages.append(Message(
            id=f"message-{call_id:08x}",
            role=MessageRole.tool,
            content=[TextContent(text=f"Inserted memory {i}")],
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_call_id=f"call_{call_id-1}",
            name="archival_memory_insert",
            created_at=datetime.now()
        ))
        call_id += 1
    
    # Finally: send() back to main agent (but this never happens because agent dies!)
    messages.append(Message(
        id=f"message-{call_id:08x}",
        role=MessageRole.assistant,
        content=[TextContent(text="")],
        agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
        tool_calls=[OpenAIToolCall(
            id=f"call_{call_id}",
            function=OpenAIFunction(
                name="send",
                arguments=json.dumps({
                    "to": "agent:agent-ed6055c1-3c50-4dae-8966-36321a827dc9",
                    "message": "Research complete: Comprehensive spider analysis stored in archival memory",
                    "request_heartbeat": False
                })
            ),
            type="function"
        )],
        created_at=datetime.now()
    ))
    call_id += 1
    
    print(f"\n=== RESEARCH AGENT DEATH SCENARIO ===")
    print(f"Total messages: {len(messages)}")
    print(f"Message breakdown:")
    print(f"  System: 1")
    print(f"  User: 1 (only the initial request from main agent)")
    print(f"  Assistant: {sum(1 for m in messages if m.role == MessageRole.assistant)}")
    print(f"  Tool: {sum(1 for m in messages if m.role == MessageRole.tool)}")
    print(f"\nCRITICAL: After index 1, there are NO user messages!")
    
    # Simulate what happens when context limit is hit
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,
        message_buffer_limit=50,  # Much smaller than our message count
        message_buffer_min=10
    )
    
    # This simulates _rebuild_context_window calling summarizer with force=True, clear=True
    trimmed, was_summarized = summarizer._static_buffer_summarization(
        in_context_messages=messages,
        new_letta_messages=[],
        force=True,
        clear=True  # This happens when context overflow detected
    )
    
    print(f"\n=== AFTER SUMMARIZATION (Context Overflow) ===")
    print(f"Trimmed message count: {len(trimmed)}")
    print(f"Message roles: {[m.role for m in trimmed]}")
    
    if len(trimmed) == 1 and trimmed[0].role == MessageRole.system:
        print("\n🔴🔴🔴 RESEARCH AGENT IS DEAD! 🔴🔴🔴")
        print("The agent has ONLY the system message - no context of:")
        print("  - What the user asked for")
        print("  - What research was done")
        print("  - What needs to be sent back")
        print("\nThis is EXACTLY what's happening in staging!")
        print("The research agent hits context limit, summarizer runs,")
        print("and the agent is left with no memory of its task!")
    
    # This is the exact bug killing the research agent
    assert len(trimmed) > 1, "Research agent needs context to function!"


def test_research_agent_with_orphaned_tool_response():
    """Test the specific case with orphaned tool response like in staging logs."""
    
    messages = []
    
    # System
    messages.append(Message(
        id="message-00000000",
        role=MessageRole.system,
        content=[TextContent(text="Research agent system prompt")],
        agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
        created_at=datetime.now()
    ))
    
    # User message from main agent
    messages.append(Message(
        id="message-00000001",
        role=MessageRole.user,
        content=[TextContent(text="[Message from agent 'main'] Research something")],
        agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
        created_at=datetime.now()
    ))
    
    # Add the orphaned tool response (like call_Hq7WodLX3wiSy1Z7Im5ywOD9 from logs)
    # This is a tool response WITHOUT its corresponding tool call!
    messages.append(Message(
        id="message-00000002",
        role=MessageRole.tool,
        content=[TextContent(text="Orphaned response from previous session")],
        agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
        tool_call_id="call_Hq7WodLX3wiSy1Z7Im5ywOD9",  # From staging error logs!
        name="archival_memory_insert",
        created_at=datetime.now()
    ))
    
    # Then normal tool calls
    for i in range(20):
        # Tool call
        messages.append(Message(
            id=f"message-{i*2+3:08x}",
            role=MessageRole.assistant,
            content=[TextContent(text="")],
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_calls=[OpenAIToolCall(
                id=f"call_{i}",
                function=OpenAIFunction(
                    name="archival_memory_insert",
                    arguments='{"content": "data"}'
                ),
                type="function"
            )],
            created_at=datetime.now()
        ))
        
        # Tool response
        messages.append(Message(
            id=f"message-{i*2+4:08x}",
            role=MessageRole.tool,
            content=[TextContent(text="Inserted")],
            agent_id="agent-e667ec69-b3cf-4841-8625-8f5dedd9c489",
            tool_call_id=f"call_{i}",
            name="archival_memory_insert",
            created_at=datetime.now()
        ))
    
    print(f"\n=== RESEARCH AGENT WITH ORPHANED RESPONSE ===")
    print(f"Total messages: {len(messages)}")
    print(f"Message at index 2 is ORPHANED tool response (no matching call)")
    
    summarizer = Summarizer(
        mode=SummarizationMode.STATIC_MESSAGE_BUFFER,
        summarizer_agent=None,
        message_buffer_limit=10,
        message_buffer_min=5
    )
    
    # This should handle the orphaned response
    trimmed, was_summarized = summarizer._static_buffer_summarization(
        in_context_messages=messages,
        new_letta_messages=[],
        force=True,
        clear=True
    )
    
    print(f"\nAfter summarization:")
    print(f"  Trimmed count: {len(trimmed)}")
    
    # Check for orphaned responses in result
    for msg in trimmed:
        if msg.role == MessageRole.tool and msg.tool_call_id == "call_Hq7WodLX3wiSy1Z7Im5ywOD9":
            print("⚠️ Orphaned response still present!")
    
    if len(trimmed) <= 1:
        print("🔴 Agent killed by summarization!")
    
    return trimmed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-k", "test_research_agent_death_scenario"])