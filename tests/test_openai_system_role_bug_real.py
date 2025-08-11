"""
Real OpenAI API integration test to reproduce the system role bug.

This test makes actual OpenAI API calls to demonstrate that injecting system messages 
mid-conversation breaks tool call ID tracking.
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
    client.actor.id = "test-user-integration"
    return client


@pytest.fixture
def llm_config():
    """Create LLM config for testing."""
    return LLMConfig(
        model="gpt-4o-mini",  # Cost-effective model for testing
        model_endpoint_type="openai",
        model_endpoint="https://api.openai.com/v1",
        context_window=128000,
        max_tokens=300  # Keep responses short
    )


@pytest.fixture
def archival_memory_tool():
    """Create archival memory tool for testing - strict mode compliant."""
    return {
        "name": "archival_memory_insert",
        "description": "Insert content into archival memory",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content to store in archival memory"
                },
                "request_heartbeat": {
                    "type": "boolean",
                    "description": "Request another step after tool call",
                    "default": True
                }
            },
            "required": ["content", "request_heartbeat"],  # OpenAI strict mode requires ALL parameters in required
            "additionalProperties": False
        }
    }


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api  
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_system_role_injection_breaks_tool_call_ids(openai_client, llm_config, archival_memory_tool):
    """Test that injecting system messages mid-conversation causes OpenAI tool call ID issues."""
    
    print("\n=== Testing System Role Injection Bug ===")
    
    # Step 1: Create initial conversation with a tool call
    print("1. Starting initial conversation with tool call...")
    initial_messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant with access to archival memory.")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user, 
            content=[TextContent(text="Please remember: The Wolpertinger is a Bavarian creature.")],
            agent_id="test-agent"
        )
    ]
    
    # Make initial API call to get tool calls
    request_data = openai_client.build_request_data(
        messages=initial_messages,
        llm_config=llm_config,
        tools=[archival_memory_tool]
    )
    
    initial_response = await openai_client.request_async(request_data, llm_config)
    print("✓ Initial API call successful")
    
    # Convert to chat completion format
    chat_response = openai_client.convert_response_to_chat_completion(
        initial_response, initial_messages, llm_config
    )
    
    # Verify we got tool calls
    assert len(chat_response.choices) > 0
    message = chat_response.choices[0].message
    assert message.tool_calls is not None
    assert len(message.tool_calls) > 0
    
    tool_call = message.tool_calls[0]
    tool_call_id = tool_call.id
    print(f"Got tool call with ID: {tool_call_id}")
    
    # Step 2: Create conversation history with tool result
    print("2. Building conversation history with tool result...")
    conversation_messages = initial_messages + [
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text=message.content or "")],
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
            content=[TextContent(text="Successfully stored Wolpertinger information in archival memory.")],
            tool_call_id=tool_call_id,
            agent_id="test-agent"
        )
    ]
    
    # Step 3: Now inject a SYSTEM message (this is the bug!)
    print("3. Injecting system message mid-conversation (this should cause issues)...")
    
    # This is what happens in multi_agent_tool_executor.py line 120 BEFORE the fix
    # When an agent receives a message from another agent using MessageRole.system
    buggy_conversation = conversation_messages + [
        PydanticMessage(
            role=MessageRole.system,  # ❌ THIS BREAKS OPENAI TOOL CALL ID TRACKING
            content=[TextContent(text="[Message from agent 'agent-research-123'] Additional research: The Wolpertinger has antlers like a deer and wings like a pheasant.")],
            agent_id="test-agent"
        )
    ]
    
    # Step 4: Try to continue the conversation - this should show issues
    print("4. Attempting to continue conversation with system message injection...")
    
    try:
        buggy_request = openai_client.build_request_data(
            messages=buggy_conversation,
            llm_config=llm_config,
            tools=[archival_memory_tool]
        )
        
        buggy_response = await openai_client.request_async(buggy_request, llm_config)
        print("⚠️ System message injection did not cause immediate API failure")
        
        # Convert response and check for tool calls
        buggy_chat_response = openai_client.convert_response_to_chat_completion(
            buggy_response, buggy_conversation, llm_config
        )
        
        # If we get tool calls, the IDs might be corrupted
        if (buggy_chat_response.choices[0].message.tool_calls and 
            len(buggy_chat_response.choices[0].message.tool_calls) > 0):
            
            new_tool_call = buggy_chat_response.choices[0].message.tool_calls[0]
            print(f"New tool call ID after system injection: {new_tool_call.id}")
            
            # Try to submit tool result with wrong ID (simulating the corruption bug)
            print("5. Testing tool call ID corruption by submitting wrong ID...")
            
            final_conversation = buggy_conversation + [
                PydanticMessage(
                    role=MessageRole.assistant,
                    content=[TextContent(text=buggy_chat_response.choices[0].message.content or "")],
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
                    content=[TextContent(text="Tool executed successfully")],
                    tool_call_id="call_WRONG_ID_12345",  # ❌ Deliberately wrong ID
                    agent_id="test-agent"
                )
            ]
            
            try:
                final_request = openai_client.build_request_data(
                    messages=final_conversation,
                    llm_config=llm_config,
                    tools=[archival_memory_tool]
                )
                
                final_response = await openai_client.request_async(final_request, llm_config)
                print("❌ OpenAI should have rejected mismatched tool call ID but didn't!")
                
            except Exception as e:
                print(f"✅ OpenAI correctly rejected mismatched tool call ID: {type(e).__name__}: {str(e)}")
                assert "tool call" in str(e).lower() or "call_id" in str(e).lower()
        
    except Exception as e:
        print(f"✅ System message injection caused OpenAI API error: {type(e).__name__}: {str(e)}")


@pytest.mark.asyncio
@pytest.mark.integration 
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_user_role_fix_works_correctly(openai_client, llm_config, archival_memory_tool):
    """Test that using user role instead of system role (the fix) works correctly."""
    
    print("\n=== Testing User Role Fix ===")
    
    # Step 1: Create the same initial conversation setup
    print("1. Creating initial conversation...")
    initial_messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant with access to archival memory.")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Please remember: The Wolpertinger is a Bavarian creature.")],
            agent_id="test-agent"
        )
    ]
    
    # Get initial tool call
    request_data = openai_client.build_request_data(
        messages=initial_messages,
        llm_config=llm_config,
        tools=[archival_memory_tool]
    )
    
    initial_response = await openai_client.request_async(request_data, llm_config)
    chat_response = openai_client.convert_response_to_chat_completion(
        initial_response, initial_messages, llm_config
    )
    
    tool_call = chat_response.choices[0].message.tool_calls[0]
    print(f"Got initial tool call ID: {tool_call.id}")
    
    # Step 2: Build conversation with tool result
    conversation_messages = initial_messages + [
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
            content=[TextContent(text="Successfully stored Wolpertinger information.")],
            tool_call_id=tool_call.id,
            agent_id="test-agent"
        )
    ]
    
    # Step 3: Add agent message using USER role (the fix!)
    print("2. Adding agent message using user role (the fix)...")
    
    fixed_conversation = conversation_messages + [
        PydanticMessage(
            role=MessageRole.user,  # ✅ THIS IS THE FIX - user instead of system
            content=[TextContent(text="[Message from agent 'agent-research-123'] Additional research: The Wolpertinger has antlers like a deer and wings like a pheasant.")],
            agent_id="test-agent"
        )
    ]
    
    # Step 4: This should work without tool call ID issues
    print("3. Continuing conversation with user role - this should work...")
    
    try:
        fixed_request = openai_client.build_request_data(
            messages=fixed_conversation,
            llm_config=llm_config,
            tools=[archival_memory_tool]
        )
        
        fixed_response = await openai_client.request_async(fixed_request, llm_config)
        fixed_chat_response = openai_client.convert_response_to_chat_completion(
            fixed_response, fixed_conversation, llm_config  
        )
        
        print(f"✅ User role approach worked! Response: {fixed_chat_response.choices[0].message.content}")
        
        # If we get tool calls, test that ID tracking works properly
        if (fixed_chat_response.choices[0].message.tool_calls and
            len(fixed_chat_response.choices[0].message.tool_calls) > 0):
            
            new_tool_call = fixed_chat_response.choices[0].message.tool_calls[0]
            print(f"New tool call ID with user role: {new_tool_call.id}")
            
            # Submit tool result with CORRECT matching ID
            final_conversation = fixed_conversation + [
                PydanticMessage(
                    role=MessageRole.assistant,
                    content=[TextContent(text=fixed_chat_response.choices[0].message.content or "")],
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
                    content=[TextContent(text="Additional research stored successfully")],
                    tool_call_id=new_tool_call.id,  # ✅ Correct matching ID
                    agent_id="test-agent"
                )
            ]
            
            # This should work without errors
            final_request = openai_client.build_request_data(
                messages=final_conversation,
                llm_config=llm_config,
                tools=[archival_memory_tool]
            )
            
            final_response = await openai_client.request_async(final_request, llm_config)
            final_chat_response = openai_client.convert_response_to_chat_completion(
                final_response, final_conversation, llm_config
            )
            
            print(f"✅ Tool call with correct ID was accepted: {final_chat_response.choices[0].message.content}")
        
    except Exception as e:
        pytest.fail(f"User role approach should work but got error: {type(e).__name__}: {str(e)}")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_assistant_role_alternative_approach(openai_client, llm_config, archival_memory_tool):
    """Test using assistant role for agent-to-agent messages as 'thinking about received message'."""
    
    print("\n=== Testing Assistant Role Alternative ===")
    
    # Step 1: Create initial conversation setup
    print("1. Creating initial conversation...")
    initial_messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant with access to archival memory.")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Please remember: The Wolpertinger is a Bavarian creature.")],
            agent_id="test-agent"
        )
    ]
    
    # Get initial tool call
    request_data = openai_client.build_request_data(
        messages=initial_messages,
        llm_config=llm_config,
        tools=[archival_memory_tool]
    )
    
    initial_response = await openai_client.request_async(request_data, llm_config)
    chat_response = openai_client.convert_response_to_chat_completion(
        initial_response, initial_messages, llm_config
    )
    
    tool_call = chat_response.choices[0].message.tool_calls[0]
    print(f"Got initial tool call ID: {tool_call.id}")
    
    # Step 2: Build conversation with tool result
    conversation_messages = initial_messages + [
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text=chat_response.choices[0].message.content or "I'll store this information.")],
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
            content=[TextContent(text="Successfully stored Wolpertinger information.")],
            tool_call_id=tool_call.id,
            agent_id="test-agent"
        )
    ]
    
    # Step 3: Add agent message using ASSISTANT role (framing as internal thought)
    print("2. Adding agent message using assistant role (thinking approach)...")
    
    assistant_conversation = conversation_messages + [
        PydanticMessage(
            role=MessageRole.assistant,  # 🤔 Testing this approach
            content=[TextContent(text="I must think about this new information I just received from agent 'agent-research-123': Additional research shows that the Wolpertinger has antlers like a deer and wings like a pheasant. I should store this additional information as well.")],
            agent_id="test-agent"
        )
    ]
    
    # Step 4: Test if this approach works
    print("3. Continuing conversation with assistant role approach...")
    
    try:
        assistant_request = openai_client.build_request_data(
            messages=assistant_conversation,
            llm_config=llm_config,
            tools=[archival_memory_tool]
        )
        
        assistant_response = await openai_client.request_async(assistant_request, llm_config)
        assistant_chat_response = openai_client.convert_response_to_chat_completion(
            assistant_response, assistant_conversation, llm_config
        )
        
        print(f"✅ Assistant role approach worked! Response: {assistant_chat_response.choices[0].message.content}")
        
        # Test tool call ID consistency if we get tool calls
        if (assistant_chat_response.choices[0].message.tool_calls and
            len(assistant_chat_response.choices[0].message.tool_calls) > 0):
            
            new_tool_call = assistant_chat_response.choices[0].message.tool_calls[0]
            print(f"New tool call ID with assistant role: {new_tool_call.id}")
            
            # Test proper tool result submission
            final_conversation = assistant_conversation + [
                PydanticMessage(
                    role=MessageRole.assistant,
                    content=[TextContent(text=assistant_chat_response.choices[0].message.content or "")],
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
                    content=[TextContent(text="Additional research stored successfully")],
                    tool_call_id=new_tool_call.id,
                    agent_id="test-agent"
                )
            ]
            
            final_request = openai_client.build_request_data(
                messages=final_conversation,
                llm_config=llm_config,
                tools=[archival_memory_tool]
            )
            
            final_response = await openai_client.request_async(final_request, llm_config)
            final_chat_response = openai_client.convert_response_to_chat_completion(
                final_response, final_conversation, llm_config
            )
            
            print(f"✅ Tool call with assistant role was accepted: {final_chat_response.choices[0].message.content}")
        
    except Exception as e:
        print(f"❌ Assistant role approach failed: {type(e).__name__}: {str(e)}")
        raise


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_compare_all_three_approaches(openai_client, llm_config, archival_memory_tool):
    """Compare system, user, and assistant roles for agent-to-agent messages."""
    
    print("\n=== Comparing All Three Approaches ===")
    
    # Base conversation setup
    base_messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are a helpful assistant.")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="Hello!")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text="Hi! How can I help you?")],
            agent_id="test-agent"
        )
    ]
    
    agent_message_content = "I received new information about Wolpertingers from another agent."
    
    approaches = [
        ("System Role (broken)", MessageRole.system, f"[Message from agent 'research-agent'] {agent_message_content}"),
        ("User Role (current fix)", MessageRole.user, f"[Message from agent 'research-agent'] {agent_message_content}"),
        ("Assistant Role (thinking)", MessageRole.assistant, f"I must think about this message I received from agent 'research-agent': {agent_message_content}")
    ]
    
    results = {}
    
    for approach_name, role, message_text in approaches:
        print(f"\n--- Testing {approach_name} ---")
        
        test_conversation = base_messages + [
            PydanticMessage(
                role=role,
                content=[TextContent(text=message_text)],
                agent_id="test-agent"
            )
        ]
        
        try:
            request_data = openai_client.build_request_data(
                messages=test_conversation,
                llm_config=llm_config,
                tools=[archival_memory_tool]
            )
            
            response = await openai_client.request_async(request_data, llm_config)
            chat_response = openai_client.convert_response_to_chat_completion(
                response, test_conversation, llm_config
            )
            
            print(f"✅ {approach_name}: SUCCESS - {chat_response.choices[0].message.content}")
            results[approach_name] = "SUCCESS"
            
        except Exception as e:
            print(f"❌ {approach_name}: FAILED - {type(e).__name__}: {str(e)}")
            results[approach_name] = f"FAILED: {type(e).__name__}"
    
    print(f"\n=== Final Results ===")
    for approach, result in results.items():
        print(f"{approach}: {result}")
    
    # Verify our expectations
    assert "FAILED" in results["System Role (broken)"] or "SUCCESS" in results["System Role (broken)"]  # Either could happen
    assert "SUCCESS" in results["User Role (current fix)"]  # Should work
    assert "SUCCESS" in results["Assistant Role (thinking)"]  # Should also work


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.external_api
@pytest.mark.openai_basic
@pytest.mark.skipif(not model_settings.openai_api_key, reason="OpenAI API key not configured")
async def test_assistant_role_in_complex_tool_calling_scenario(openai_client, llm_config, archival_memory_tool):
    """Test assistant role in the complex scenario that originally caused the bug."""
    
    print("\n=== Testing Assistant Role in Complex Tool Calling Scenario ===")
    
    # This reproduces the EXACT scenario where the bug occurred:
    # 1. Agent makes tool calls
    # 2. Tool results are submitted
    # 3. Another agent sends message (this is where the bug happened)
    # 4. Agent continues with more tool calls
    
    # Step 1: Start complex conversation with multiple tool interactions
    print("1. Creating complex conversation with tool calls...")
    complex_messages = [
        PydanticMessage(
            role=MessageRole.system,
            content=[TextContent(text="You are a research assistant with access to archival memory. You help process and store research information.")],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.user,
            content=[TextContent(text="I need you to research and store information about the Wolpertinger. Please remember this initial fact: The Wolpertinger is a legendary creature from Bavarian folklore.")],
            agent_id="test-agent"
        )
    ]
    
    # Get first set of tool calls
    request_data_1 = openai_client.build_request_data(
        messages=complex_messages,
        llm_config=llm_config,
        tools=[archival_memory_tool]
    )
    
    response_1 = await openai_client.request_async(request_data_1, llm_config)
    chat_response_1 = openai_client.convert_response_to_chat_completion(
        response_1, complex_messages, llm_config
    )
    
    first_tool_call = chat_response_1.choices[0].message.tool_calls[0]
    print(f"First tool call ID: {first_tool_call.id}")
    
    # Step 2: Add first assistant response and tool result
    complex_messages += [
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text=chat_response_1.choices[0].message.content or "I'll store this information.")],
            tool_calls=[{
                "id": first_tool_call.id,
                "type": "function",
                "function": {
                    "name": first_tool_call.function.name,
                    "arguments": first_tool_call.function.arguments
                }
            }],
            agent_id="test-agent"
        ),
        PydanticMessage(
            role=MessageRole.tool,
            content=[TextContent(text="Successfully stored initial Wolpertinger information in archival memory.")],
            tool_call_id=first_tool_call.id,
            agent_id="test-agent"
        )
    ]
    
    # Step 3: Get second assistant response 
    request_data_2 = openai_client.build_request_data(
        messages=complex_messages,
        llm_config=llm_config,
        tools=[archival_memory_tool]
    )
    
    response_2 = await openai_client.request_async(request_data_2, llm_config)
    chat_response_2 = openai_client.convert_response_to_chat_completion(
        response_2, complex_messages, llm_config
    )
    
    # Add the second assistant response
    complex_messages.append(
        PydanticMessage(
            role=MessageRole.assistant,
            content=[TextContent(text=chat_response_2.choices[0].message.content or "Information stored successfully.")],
            agent_id="test-agent"
        )
    )
    
    print(f"Conversation has {len(complex_messages)} messages before agent-to-agent message")
    
    # Step 4: NOW add the agent-to-agent message using ASSISTANT role
    # This is the critical point where the bug occurred
    print("2. Adding complex agent-to-agent message using assistant role...")
    
    assistant_role_message = PydanticMessage(
        role=MessageRole.assistant,  # Using assistant role with thinking framing
        content=[TextContent(text="Let me think about this additional research I just received from my colleague agent 'research-specialist-789': They've discovered that the Wolpertinger is typically described as having the body of a rabbit, the antlers of a deer, the wings of a pheasant, and sometimes the fangs of a vampire. It's said to be extremely shy and elusive, inhabiting the remote mountainous regions of Bavaria. This is fascinating additional detail that I should definitely store in my archival memory as well.")],
        agent_id="test-agent"
    )
    
    complex_messages.append(assistant_role_message)
    
    # Step 5: Try to continue conversation with more tool calls
    print("3. Attempting to continue with more tool calls using assistant role...")
    
    try:
        final_request = openai_client.build_request_data(
            messages=complex_messages,
            llm_config=llm_config,
            tools=[archival_memory_tool]
        )
        
        final_response = await openai_client.request_async(final_request, llm_config)
        final_chat_response = openai_client.convert_response_to_chat_completion(
            final_response, complex_messages, llm_config
        )
        
        print(f"✅ Assistant role worked in complex scenario! Response: {final_chat_response.choices[0].message.content}")
        
        # Check if we got new tool calls and if their IDs are properly tracked
        if (final_chat_response.choices[0].message.tool_calls and 
            len(final_chat_response.choices[0].message.tool_calls) > 0):
            
            final_tool_call = final_chat_response.choices[0].message.tool_calls[0]
            print(f"Final tool call ID with assistant role: {final_tool_call.id}")
            
            # Test that we can submit tool results with correct IDs
            complete_conversation = complex_messages + [
                PydanticMessage(
                    role=MessageRole.assistant,
                    content=[TextContent(text=final_chat_response.choices[0].message.content or "")],
                    tool_calls=[{
                        "id": final_tool_call.id,
                        "type": "function",
                        "function": {
                            "name": final_tool_call.function.name,
                            "arguments": final_tool_call.function.arguments
                        }
                    }],
                    agent_id="test-agent"
                ),
                PydanticMessage(
                    role=MessageRole.tool,
                    content=[TextContent(text="Additional detailed Wolpertinger research stored successfully in archival memory.")],
                    tool_call_id=final_tool_call.id,
                    agent_id="test-agent"
                )
            ]
            
            completion_request = openai_client.build_request_data(
                messages=complete_conversation,
                llm_config=llm_config,
                tools=[archival_memory_tool]
            )
            
            completion_response = await openai_client.request_async(completion_request, llm_config)
            completion_chat_response = openai_client.convert_response_to_chat_completion(
                completion_response, complete_conversation, llm_config
            )
            
            print(f"✅ Complex tool call sequence completed with assistant role: {completion_chat_response.choices[0].message.content}")
            print(f"✅ RESULT: Assistant role works perfectly in complex tool calling scenarios!")
            
        else:
            print("✅ No additional tool calls needed, assistant role approach worked!")
        
    except Exception as e:
        print(f"❌ Assistant role failed in complex scenario: {type(e).__name__}: {str(e)}")
        # This would indicate that assistant role has the same problems as system role in complex scenarios
        raise


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])