# Proactive Messaging and Real-time Agent Communication

## Overview

This document outlines Letta's current capabilities for proactive messaging (unsolicited agent messages) and proposes enhancements for real-time delivery to external clients. Currently, Letta has robust infrastructure for agents to generate proactive messages, but lacks real-time push mechanisms for external clients who need to forward these messages to end users.

## Current State Analysis

### ✅ Existing Proactive Messaging Infrastructure

#### 1. Background Job Scheduling System
**Location**: `letta/jobs/scheduler.py`

- **APScheduler integration** with AsyncIOScheduler and PostgreSQL advisory locks
- **Distributed scheduling** with leader election across multiple server instances
- **Extensible job types** currently focused on LLM batch processing
- **Interval-based execution** for periodic agent tasks

```python
scheduler = AsyncIOScheduler()
scheduler.add_job(
    poll_running_llm_batches,
    trigger=IntervalTrigger(seconds=settings.poll_running_llm_batches_interval_seconds),
    id="poll_llm_batches",
    name="Poll LLM API batch jobs"
)
```

#### 2. Multi-Agent Coordination Tools
**Location**: `letta/functions/function_sets/multi_agent.py`

Agents can proactively communicate with each other:
- `send_message_to_agent_async()` - Fire-and-forget inter-agent messaging
- `send_message_to_agent_and_wait_for_reply()` - Request-response patterns
- `send_message_to_agents_matching_tags()` - Broadcast to tagged agents
- `send_message_to_all_agents_in_group()` - Group messaging

#### 3. Sleeptime Multi-Agent System
**Location**: `letta/groups/sleeptime_multi_agent_v2.py`

- **Frequency-based activation**: Agents automatically participate every N conversation turns
- **Background task creation**: Async tasks created when activation conditions are met
- **Proactive conversation participation**: Agents analyze transcripts and respond unprompted

#### 4. Optimized Message Retrieval
**Location**: `letta/server/rest_api/routers/v1/agents.py:603-633`

Current REST API already supports efficient polling:
```http
GET /v1/agents/{agent_id}/messages?after={last_message_id}&limit=10
```

**Key features:**
- Cursor-based pagination for efficiency
- "Messages after ID X" pattern optimization
- Minimal data transfer for polling clients

#### 5. WebSocket Infrastructure
**Location**: `letta/server/ws_api/`

- **Real-time bidirectional communication** with WebSocket server on port 8283
- **Multi-client broadcasting** capabilities
- **Agent interfaces**: `SyncWebSocketInterface` and `AsyncWebSocketInterface`
- **Push notification support** for connected clients

#### 6. Server-Sent Events (SSE) Streaming
**Location**: `letta/server/rest_api/routers/v1/agents.py:725-826`

- **POST-triggered streaming** for message responses
- **Real-time agent response delivery** via `text/event-stream`
- **Multiple message types**: ReasoningMessage, AssistantMessage, ToolCallMessage, etc.

#### 7. External Integration Patterns
**Location**: `examples/personal_assistant_demo/gmail_unread_polling_listener.py`

Example of external systems injecting proactive messages:
```python
def route_reply_to_letta_api(message):
    url = f"{MEMGPT_SERVER_URL}/api/agents/{MEMGPT_AGENT_ID}/messages"
    data = {"role": "system", "message": f"[EMAIL NOTIFICATION] {message}"}
    requests.post(url, headers=headers, json=data)
```

### ❌ Current Limitations

#### 1. No Real-time Push for Unsolicited Messages
- **SSE endpoints require POST** (user-initiated message)
- **WebSocket server lacks subscription mode** for passive message listening
- **No streaming endpoint** for unsolicited agent messages

#### 2. External Clients Must Poll
- Clients need to periodically check for new messages
- No push notifications when agents send proactive messages
- Potential latency between agent action and client awareness

## Use Case: External Client Integration

### Problem Statement
External clients (mobile apps, web applications, chatbots) need to:
1. **Receive unsolicited agent messages** in real-time
2. **Forward messages to end users** immediately when agents are proactive
3. **Avoid polling overhead** while maintaining responsiveness
4. **Handle high-frequency agent communication** efficiently

### Current Workaround
```javascript
// Clients currently must poll
async function pollForNewMessages(agentId, lastMessageId) {
  const response = await fetch(
    `/v1/agents/${agentId}/messages?after=${lastMessageId}&limit=50`
  );
  return response.json();
}

// Poll every 5 seconds
setInterval(() => pollForNewMessages(agentId, lastSync), 5000);
```

## Proposed Implementation Plan

### Phase 1: WebSocket Message Subscriptions (Minimal Changes)

#### 1.1 Extend WebSocket Protocol
**File**: `letta/server/ws_api/protocol.py`

Add subscription message types:
```python
def client_subscribe_messages(agent_id: str, after: str = None):
    """Client requests to subscribe to agent messages"""
    return json.dumps({
        "type": "subscribe_messages",
        "agent_id": agent_id,
        "after": after  # Optional: only messages after this ID
    })

def client_unsubscribe_messages(agent_id: str):
    """Client requests to unsubscribe from agent messages"""
    return json.dumps({
        "type": "unsubscribe_messages",
        "agent_id": agent_id
    })

def server_unsolicited_message(agent_id: str, message: dict):
    """Server pushes unsolicited agent message to subscribers"""
    return json.dumps({
        "type": "unsolicited_message",
        "agent_id": agent_id,
        "message": message,
        "timestamp": datetime.utcnow().isoformat()
    })

def server_subscription_confirmed(agent_id: str):
    """Server confirms subscription setup"""
    return json.dumps({
        "type": "subscription_confirmed",
        "agent_id": agent_id
    })
```

#### 1.2 Extend WebSocket Server
**File**: `letta/server/ws_api/server.py`

Add subscription management:
```python
class WebSocketConnectionManager:
    def __init__(self):
        self.connections: Dict[WebSocket, Set[str]] = {}  # websocket -> subscribed agent IDs
        self.agent_subscribers: Dict[str, Set[WebSocket]] = {}  # agent_id -> subscriber websockets
    
    async def subscribe_to_agent(self, websocket: WebSocket, agent_id: str, after: str = None):
        """Subscribe websocket to agent messages"""
        if websocket not in self.connections:
            self.connections[websocket] = set()
        
        self.connections[websocket].add(agent_id)
        
        if agent_id not in self.agent_subscribers:
            self.agent_subscribers[agent_id] = set()
        self.agent_subscribers[agent_id].add(websocket)
        
        # Send recent messages if 'after' specified
        if after:
            await self._send_recent_messages(websocket, agent_id, after)
        
        # Confirm subscription
        await websocket.send_text(protocol.server_subscription_confirmed(agent_id))
    
    async def notify_agent_message(self, agent_id: str, message: dict):
        """Push message to all subscribers of this agent"""
        if agent_id in self.agent_subscribers:
            message_data = protocol.server_unsolicited_message(agent_id, message)
            await asyncio.gather(*[
                ws.send_text(message_data) 
                for ws in self.agent_subscribers[agent_id]
            ], return_exceptions=True)
```

#### 1.3 Integration with Existing Systems
**Files**: Various proactive messaging locations

Hook into existing proactive message creation:
```python
# In sleeptime_multi_agent_v2.py
async def _participant_agent_step(self, agent_id: str, ...):
    # ... existing logic ...
    
    # After agent sends message, notify WebSocket subscribers
    if websocket_manager:
        await websocket_manager.notify_agent_message(agent_id, message_data)

# In multi_agent.py
def send_message_to_agent_async(self, message: str, other_agent_id: str):
    # ... existing logic ...
    
    # Notify subscribers of the target agent
    asyncio.create_task(
        websocket_manager.notify_agent_message(other_agent_id, message_data)
    )
```

### Phase 2: Server-Sent Events Subscription Endpoint

#### 2.1 New SSE Endpoint
**File**: `letta/server/rest_api/routers/v1/agents.py`

```python
@router.get("/{agent_id}/messages/subscribe")
async def subscribe_to_agent_messages(
    agent_id: str,
    after: Optional[str] = Query(None, description="Only messages after this ID"),
    request: Request,
    server: "SyncServer" = Depends(get_letta_server),
    user_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """
    Subscribe to real-time agent messages via Server-Sent Events.
    Returns unsolicited messages as they are generated by the agent.
    """
    
    async def message_stream():
        # Send any recent messages first if 'after' specified
        if after:
            recent_messages = await server.get_agent_messages(
                user_id=user_id, 
                agent_id=agent_id, 
                after=after
            )
            for msg in recent_messages:
                yield f"data: {json.dumps(msg.model_dump())}\n\n"
        
        # Set up subscription for new messages
        subscription_id = f"{agent_id}_{user_id}_{datetime.utcnow().timestamp()}"
        message_queue = asyncio.Queue()
        
        # Register subscription
        await server.subscribe_to_agent_messages(agent_id, subscription_id, message_queue)
        
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                try:
                    # Wait for new message with timeout
                    message = await asyncio.wait_for(message_queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield "data: {\"type\": \"keepalive\"}\n\n"
                    
        finally:
            # Clean up subscription
            await server.unsubscribe_from_agent_messages(agent_id, subscription_id)
    
    return StreamingResponse(
        message_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )
```

#### 2.2 Server Subscription Management
**File**: `letta/server/server.py`

```python
class SyncServer:
    def __init__(self):
        self.message_subscriptions: Dict[str, Dict[str, asyncio.Queue]] = {}  # agent_id -> {sub_id -> queue}
    
    async def subscribe_to_agent_messages(self, agent_id: str, subscription_id: str, message_queue: asyncio.Queue):
        """Register a subscription for agent messages"""
        if agent_id not in self.message_subscriptions:
            self.message_subscriptions[agent_id] = {}
        self.message_subscriptions[agent_id][subscription_id] = message_queue
    
    async def unsubscribe_from_agent_messages(self, agent_id: str, subscription_id: str):
        """Remove a message subscription"""
        if agent_id in self.message_subscriptions:
            self.message_subscriptions[agent_id].pop(subscription_id, None)
            
            # Clean up empty agent subscriptions
            if not self.message_subscriptions[agent_id]:
                del self.message_subscriptions[agent_id]
    
    async def broadcast_agent_message(self, agent_id: str, message: dict):
        """Send message to all subscribers of this agent"""
        if agent_id in self.message_subscriptions:
            # Send to all subscription queues for this agent
            for queue in self.message_subscriptions[agent_id].values():
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    # Log warning about full queue
                    pass
```

### Phase 3: Enhanced Features

#### 3.1 Message Filtering and Routing
- **Message type filtering**: Subscribe only to specific message types
- **Priority-based delivery**: High-priority messages bypass queues
- **User-specific routing**: Messages targeted to specific users

#### 3.2 Reliability and Error Handling
- **Message acknowledgment**: Ensure delivery confirmation
- **Retry mechanisms**: Resend failed deliveries
- **Dead letter queues**: Handle permanently failed deliveries
- **Connection recovery**: Resume subscriptions after disconnection

#### 3.3 Performance Optimizations
- **Message batching**: Group multiple messages for efficiency
- **Compression**: Reduce bandwidth for large message volumes
- **Rate limiting**: Prevent message flooding
- **Subscription limits**: Limit concurrent subscriptions per client

## Implementation Considerations

### Security
- **Authentication**: Verify user access to agent messages
- **Authorization**: Ensure users can only subscribe to their own agents
- **Rate limiting**: Prevent subscription abuse
- **Input validation**: Sanitize subscription parameters

### Performance
- **Memory management**: Limit subscription queue sizes
- **Connection limits**: Maximum concurrent WebSocket/SSE connections
- **Message batching**: Optimize for high-frequency scenarios
- **Database impact**: Minimize additional queries for subscription management

### Monitoring
- **Subscription metrics**: Track active subscriptions per agent
- **Message delivery metrics**: Success/failure rates
- **Performance metrics**: Latency, throughput, queue depths
- **Error logging**: Failed deliveries, connection issues

## Client Usage Examples

### WebSocket Subscription
```javascript
const ws = new WebSocket('ws://localhost:8283');

// Subscribe to agent messages
ws.send(JSON.stringify({
    type: 'subscribe_messages',
    agent_id: 'agent-123',
    after: 'msg-456'  // Optional: only new messages
}));

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'subscription_confirmed') {
        console.log('Subscribed to agent:', data.agent_id);
    } else if (data.type === 'unsolicited_message') {
        // Forward to end user
        forwardMessageToUser(data.agent_id, data.message);
    }
};
```

### Server-Sent Events Subscription
```javascript
const eventSource = new EventSource('/v1/agents/agent-123/messages/subscribe?after=msg-456');

eventSource.onmessage = (event) => {
    const message = JSON.parse(event.data);
    
    if (message.type !== 'keepalive') {
        // Forward unsolicited message to end user
        forwardMessageToUser(message);
    }
};

eventSource.onerror = (error) => {
    console.error('SSE connection error:', error);
    // Implement reconnection logic
};
```

## Migration Strategy

### Backward Compatibility
- **Existing polling endpoints remain unchanged**
- **New subscription endpoints are additive**
- **Gradual migration path** for existing clients

### Rollout Plan
1. **Phase 1**: WebSocket subscriptions (minimal server changes)
2. **Phase 2**: SSE subscription endpoint (broader client support)
3. **Phase 3**: Enhanced features and optimizations
4. **Phase 4**: Deprecate polling recommendations (optional)

## Future Enhancements

### Advanced Subscription Features
- **Conditional subscriptions**: Filter messages by content, priority, or metadata
- **Subscription groups**: Manage multiple agent subscriptions efficiently
- **Message transformation**: Server-side filtering and formatting

### Integration Possibilities
- **Webhook delivery**: HTTP callbacks as alternative to real-time connections
- **Message queuing systems**: Redis, RabbitMQ integration for enterprise scaling
- **Cloud messaging**: Push notifications via Firebase, APNs, etc.

## Conclusion

Letta already has excellent infrastructure for generating proactive agent messages through sleeptime agents, multi-agent coordination, and background scheduling. The missing piece is real-time delivery to external clients.

The proposed WebSocket subscription extension requires minimal changes to existing code while providing immediate value. The SSE subscription endpoint offers broader client compatibility. Both approaches leverage Letta's existing strengths while solving the real-time delivery gap.

This enhancement would make Letta significantly more suitable for production deployments requiring responsive agent interactions and would eliminate the need for inefficient polling patterns.