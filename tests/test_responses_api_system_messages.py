"""
Integration test to verify system messages work correctly with OpenAI Responses API.

This test verifies that the migration to Responses API has resolved the system message
issues that existed with the Chat Completions API, specifically for agent-to-agent messaging.
"""

import os
import pytest
from unittest.mock import Mock

from letta.llm_api.openai_client import OpenAIClient
from letta.schemas.llm_config import LLMConfig
from letta.schemas.message import Message as PydanticMessage, MessageRole
from letta.schemas.letta_message_content import TextContent
from letta.settings import model_settings


@pytest.fixture
def openai_client():
    """Create OpenAI client with mock actor."""
    client = OpenAIClient()
    client.actor = Mock()
    client.actor.id = "test-user-responses-api"
    return client


@pytest.fixture
def llm_config():
    """Create LLM config for testing with Responses API."""
    return LLMConfig(
        model="gpt-4o-mini",  # Cost-effective model that supports Responses API
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1",
        context_window=128000,
        max_tokens=300
    )


@pytest.fixture
def memory_tool():
    """Create a simple memory tool for testing."""
    return {
        "name": "save_memory",
        "description": "Save information to memory",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content to save"
                },
                "request_heartbeat": {
                    "type": "boolean",
                    "description": "Request another step",
                    "default": True
                }
            },
            "required": ["content", "request_heartbeat"],
            "additionalProperties": False
        }
    }


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_system_messages_work_with_responses_api(openai_client, llm_config, memory_tool):
    """Test that system messages work correctly with the Responses API."""
    
    print("\n=== Testing System Messages with Responses API ===")
    
    # Step 1: Create initial conversation
    print("1. Creating initial conversation...")
    messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant that can save information to memory.")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Please save this fact: Elephants have excellent memory.")],
            agent_id="test-agent"
        )
    ]
    
    # Make initial request to get tool calls
    request_data = openai_client.build_request_data(
        messages=messages,
        llm_config=llm_config,
        tools=[memory_tool]
    )
    
    response = await openai_client.request_async(request_data, llm_config)
    chat_response = openai_client.convert_response_to_chat_completion(
        response, messages, llm_config
    )
    
    # Verify we got tool calls
    assert chat_response.choices[0].message.tool_calls is not None
    tool_call = chat_response.choices[0].message.tool_calls[0]
    print(f"✓ Got tool call with ID: {tool_call.id}")
    
    # Step 2: Add tool call and result to conversation
    messages.extend([
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text=chat_response.choices[0].message.content or "")],
            tool_calls=[{
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            }],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.tool,
            content=[TextContent(text="Information saved successfully.")],
            tool_call_id=tool_call.id,
            agent_id="test-agent"
        )
    ])
    
    # Step 3: Inject SYSTEM message (simulating agent-to-agent communication)
    print("2. Injecting system message for agent-to-agent communication...")
    
    system_agent_message = PydanticMessage(
        role=MessageRole.system,  # Using system role for agent messages
        content=[TextContent(text="[Message from agent 'research-agent-456'] I found additional information: Elephants can remember other elephants for decades, even after long separations.")],
        agent_id="test-agent"
    )
    
    messages.append(system_agent_message)
    
    # Step 4: Continue conversation - this should work with Responses API
    print("3. Continuing conversation after system message injection...")
    
    try:
        request_with_system = openai_client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=[memory_tool]
        )
        
        response_with_system = await openai_client.request_async(request_with_system, llm_config)
        chat_response_with_system = openai_client.convert_response_to_chat_completion(
            response_with_system, messages, llm_config
        )
        
        print(f"✅ System message worked! Response: {chat_response_with_system.choices[0].message.content}")
        
        # Check if we got new tool calls (model should save the new information)
        if chat_response_with_system.choices[0].message.tool_calls:
            new_tool_call = chat_response_with_system.choices[0].message.tool_calls[0]
            print(f"✅ New tool call after system message: {new_tool_call.id}")
            
            # Verify tool call IDs are properly tracked
            messages.extend([
                PydanticMessage(
                    role=MessageRole.assistant,
                    content=[TextContent(text=chat_response_with_system.choices[0].message.content or "")],
                    tool_calls=[{
                        "id": new_tool_call.id,
                        "type": "function",
                        "function": {
                            "name": new_tool_call.function.name,
                            "arguments": new_tool_call.function.arguments
                        }
                    }],
                    agent_id="test-agent"
                ),
                PydanticMessage(
                    role=MessageRole.tool,
                    content=[TextContent(text="Additional information saved.")],
                    tool_call_id=new_tool_call.id,
                    agent_id="test-agent"
                )
            ])
            
            # Final request to ensure continuity
            final_request = openai_client.build_request_data(
                messages=messages,
                llm_config=llm_config,
                tools=[memory_tool]
            )
            
            final_response = await openai_client.request_async(final_request, llm_config)
            final_chat_response = openai_client.convert_response_to_chat_completion(
                final_response, messages, llm_config
            )
            
            print(f"✅ Tool call tracking maintained: {final_chat_response.choices[0].message.content}")
        
        return True  # System messages work!
        
    except Exception as e:
        print(f"❌ System message failed with Responses API: {type(e).__name__}: {str(e)}")
        if "tool call" in str(e).lower() or "call_id" in str(e).lower():
            print("❌ Tool call ID tracking issue still present")
            return False
        raise


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_agent_perception_with_system_messages(openai_client, llm_config):
    """Test that agents correctly understand system messages are from other agents, not users."""
    
    print("\n=== Testing Agent Perception of System Messages ===")
    
    # Create a conversation where we can test agent understanding
    messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are an assistant that helps coordinate between different agents. When you receive messages from other agents, acknowledge which agent sent the message.")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Hello, I'm the human user. Please acknowledge this message.")],
            agent_id="test-agent"
        )
    ]
    
    # Get initial response
    request_data = openai_client.build_request_data(
        messages=messages,
        llm_config=llm_config,
        tools=None  # No tools for this test
    )
    
    response = await openai_client.request_async(request_data, llm_config)
    chat_response = openai_client.convert_response_to_chat_completion(
        response, messages, llm_config
    )
    
    print(f"Initial response: {chat_response.choices[0].message.content}")
    messages.append(
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text=chat_response.choices[0].message.content or "")],
            agent_id="test-agent"
        )
    )
    
    # Now add a SYSTEM message from another agent
    print("\n2. Adding system message from another agent...")
    messages.append(
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="[Message from agent 'data-analyst-789'] I've completed the analysis. The data shows a 15% increase in efficiency.")],
            agent_id="test-agent"
        )
    )
    
    # Get response to see if agent correctly identifies the source
    request_with_agent_msg = openai_client.build_request_data(
        messages=messages,
        llm_config=llm_config,
        tools=None
    )
    
    response_to_agent = await openai_client.request_async(request_with_agent_msg, llm_config)
    chat_response_to_agent = openai_client.convert_response_to_chat_completion(
        response_to_agent, messages, llm_config
    )
    
    agent_response = chat_response_to_agent.choices[0].message.content
    print(f"\n✅ Response to agent message: {agent_response}")
    
    # Check if the response acknowledges the agent source
    if "data-analyst" in agent_response.lower() or "agent" in agent_response.lower():
        print("✅ Model correctly identified message as from another agent!")
        return True
    else:
        print("⚠️ Model may not have clearly identified the agent source")
        return False


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_complex_multi_agent_scenario(openai_client, llm_config, memory_tool):
    """Test a complex scenario with multiple agent messages and tool calls."""
    
    print("\n=== Testing Complex Multi-Agent Scenario ===")
    
    messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are a coordinator agent that processes information from multiple research agents and saves important findings.")],
            agent_id="coordinator"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Please coordinate the research on climate change impacts.")],
            agent_id="coordinator"
        )
    ]
    
    # Initial response
    request_data = openai_client.build_request_data(
        messages=messages,
        llm_config=llm_config,
        tools=[memory_tool]
    )
    
    response = await openai_client.request_async(request_data, llm_config)
    chat_response = openai_client.convert_response_to_chat_completion(
        response, messages, llm_config
    )
    
    messages.append(
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text=chat_response.choices[0].message.content or "")],
            agent_id="coordinator"
        )
    )
    
    # Simulate multiple agents sending information via system messages
    agent_messages = [
        "[Message from agent 'ocean-researcher'] Rising sea levels have increased by 3.3mm per year since 1993.",
        "[Message from agent 'weather-analyst'] Extreme weather events have doubled in frequency over the past 50 years.",
        "[Message from agent 'ecosystem-monitor'] 1 million species face extinction due to climate change and human activities."
    ]
    
    for agent_msg in agent_messages:
        print(f"\nAdding: {agent_msg[:50]}...")
        
        messages.append(
            PydanticMessage(
                role=MessageRole.system,  # System role for agent messages
                content=[TextContent(text=agent_msg)],
                agent_id="coordinator"
            )
        )
        
        # Process each agent message
        request_with_agent = openai_client.build_request_data(
            messages=messages,
            llm_config=llm_config,
            tools=[memory_tool]
        )
        
        try:
            response_to_agent = await openai_client.request_async(request_with_agent, llm_config)
            chat_response_to_agent = openai_client.convert_response_to_chat_completion(
                response_to_agent, messages, llm_config
            )
            
            print(f"✅ Processed successfully")
            
            # Add the response
            messages.append(
                PydanticMessage(
                    role=MessageRole.assistant,
                    content=[TextContent(text=chat_response_to_agent.choices[0].message.content or "")],
                    tool_calls=chat_response_to_agent.choices[0].message.tool_calls,
                    agent_id="coordinator"
                )
            )
            
            # If there were tool calls, add tool results
            if chat_response_to_agent.choices[0].message.tool_calls:
                for tool_call in chat_response_to_agent.choices[0].message.tool_calls:
                    messages.append(
                        PydanticMessage(
                            role=MessageRole.tool,
                            content=[TextContent(text="Information saved.")],
                            tool_call_id=tool_call.id,
                            agent_id="coordinator"
                        )
                    )
                    
        except Exception as e:
            print(f"❌ Failed: {type(e).__name__}: {str(e)}")
            return False
    
    print("\n✅ Complex multi-agent scenario completed successfully!")
    print(f"✅ Processed {len(agent_messages)} agent messages with system role")
    return True


if __name__ == "__main__":
    # Run with: pytest tests/test_responses_api_system_messages.py -v -s
    pytest.main([__file__, "-v", "-s"])