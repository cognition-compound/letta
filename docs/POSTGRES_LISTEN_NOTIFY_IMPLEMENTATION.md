# PostgreSQL LISTEN/NOTIFY Implementation Guide for Real-Time Letta Messages

This guide provides a complete implementation reference for using PostgreSQL's LISTEN/NOTIFY feature to receive real-time notifications when new messages are created in Letta, eliminating the need for polling.

## Overview

PostgreSQL's LISTEN/NOTIFY provides a lightweight publish/subscribe mechanism that allows your client to receive immediate notifications when new messages are inserted into the database. This approach offers:

- **Sub-millisecond latency** - Direct database-level notifications
- **Zero polling overhead** - No repeated API calls
- **Guaranteed delivery** - All inserts trigger notifications
- **Simple implementation** - Uses standard PostgreSQL features

## Prerequisites

- PostgreSQL 9.0 or higher (Letta already uses PostgreSQL)
- A PostgreSQL client library that supports LISTEN/NOTIFY (e.g., `pg` for Node.js, `asyncpg` for Python)
- Access to create triggers on the Letta database (one-time setup)

## Database Setup

### 1. Create the Notification Function

First, create a PL/pgSQL function that will send notifications when messages are inserted:

```sql
CREATE OR REPLACE FUNCTION notify_new_message()
RETURNS trigger AS $$
DECLARE
  payload json;
BEGIN
  -- Build the notification payload
  payload = json_build_object(
    'message_id', NEW.id,
    'agent_id', NEW.agent_id,
    'user_id', NEW.user_id,
    'role', NEW.role,
    'sequence_id', NEW.sequence_id,
    'created_at', NEW.created_at,
    'organization_id', NEW.organization_id
  );
  
  -- Send notification on channel 'new_message' with the payload
  PERFORM pg_notify('new_message', payload::text);
  
  -- Also send agent-specific notifications for filtering
  PERFORM pg_notify('new_message_' || NEW.agent_id, payload::text);
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### 2. Create the Trigger

Create a trigger that fires after every insert on the messages table:

```sql
CREATE TRIGGER message_insert_notify
AFTER INSERT ON message
FOR EACH ROW
EXECUTE FUNCTION notify_new_message();
```

### 3. Optional: Create Indexes for Performance

If you'll be querying messages by sequence_id frequently:

```sql
CREATE INDEX IF NOT EXISTS idx_message_agent_sequence 
ON message(agent_id, sequence_id DESC);
```

## Client Implementation Examples

### Node.js/TypeScript Implementation

```typescript
import pg from 'pg';
import { EventEmitter } from 'events';

interface MessageNotification {
  message_id: string;
  agent_id: string;
  user_id: string;
  role: string;
  sequence_id: number;
  created_at: string;
  organization_id: string;
}

class LettaMessageListener extends EventEmitter {
  private client: pg.Client;
  private connected: boolean = false;
  private reconnectInterval: number = 5000;
  private reconnectTimer?: NodeJS.Timeout;

  constructor(private connectionString: string) {
    super();
    this.client = new pg.Client(connectionString);
  }

  async connect(): Promise<void> {
    try {
      await this.client.connect();
      this.connected = true;
      
      // Set up notification listener
      this.client.on('notification', (msg) => {
        if (msg.payload) {
          try {
            const payload: MessageNotification = JSON.parse(msg.payload);
            this.emit('message', payload);
            
            // Emit agent-specific events
            if (msg.channel.startsWith('new_message_')) {
              this.emit(`agent:${payload.agent_id}`, payload);
            }
          } catch (error) {
            this.emit('error', new Error(`Failed to parse notification: ${error}`));
          }
        }
      });

      // Handle connection errors
      this.client.on('error', (err) => {
        this.emit('error', err);
        this.handleDisconnect();
      });

      // Listen to channels
      await this.client.query('LISTEN new_message');
      
      this.emit('connected');
    } catch (error) {
      this.emit('error', error);
      this.handleDisconnect();
    }
  }

  async listenToAgent(agentId: string): Promise<void> {
    if (!this.connected) {
      throw new Error('Not connected to database');
    }
    await this.client.query(`LISTEN new_message_${agentId}`);
  }

  async stopListeningToAgent(agentId: string): Promise<void> {
    if (!this.connected) {
      throw new Error('Not connected to database');
    }
    await this.client.query(`UNLISTEN new_message_${agentId}`);
  }

  private handleDisconnect(): void {
    this.connected = false;
    this.emit('disconnected');
    
    // Attempt to reconnect
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = undefined;
        this.connect().catch(err => {
          console.error('Reconnection failed:', err);
          this.handleDisconnect();
        });
      }, this.reconnectInterval);
    }
  }

  async disconnect(): Promise<void> {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
    
    if (this.connected) {
      await this.client.end();
      this.connected = false;
    }
  }
}

// Usage example
async function main() {
  const listener = new LettaMessageListener(process.env.LETTA_PG_URI!);
  
  // Set up event handlers
  listener.on('connected', () => {
    console.log('Connected to PostgreSQL notifications');
  });
  
  listener.on('message', async (notification: MessageNotification) => {
    console.log('New message:', notification);
    
    // Fetch the full message content using Letta API
    const fullMessage = await fetchMessageById(notification.message_id);
    await processMessage(fullMessage);
  });
  
  listener.on('error', (error) => {
    console.error('Listener error:', error);
  });
  
  // Connect and start listening
  await listener.connect();
  
  // Listen to specific agents
  await listener.listenToAgent('agent-123');
}
```

### Python Implementation (asyncio)

```python
import asyncio
import json
import asyncpg
from typing import Dict, Callable, Optional
from datetime import datetime

class LettaMessageListener:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.connection: Optional[asyncpg.Connection] = None
        self.callbacks: Dict[str, Callable] = {}
        self.running = False
        self.reconnect_interval = 5

    async def connect(self):
        """Establish connection to PostgreSQL"""
        try:
            self.connection = await asyncpg.connect(self.database_url)
            await self.connection.add_listener('new_message', self._handle_notification)
            self.running = True
            print("Connected to PostgreSQL notifications")
        except Exception as e:
            print(f"Connection failed: {e}")
            await self._schedule_reconnect()

    async def _handle_notification(self, connection, pid, channel, payload):
        """Handle incoming notifications"""
        try:
            data = json.loads(payload)
            
            # Call global message callback
            if 'on_message' in self.callbacks:
                await self.callbacks['on_message'](data)
            
            # Call agent-specific callbacks
            agent_id = data.get('agent_id')
            if agent_id and f'agent:{agent_id}' in self.callbacks:
                await self.callbacks[f'agent:{agent_id}'](data)
                
        except Exception as e:
            print(f"Error handling notification: {e}")

    async def listen_to_agent(self, agent_id: str):
        """Start listening to a specific agent's messages"""
        if not self.connection:
            raise RuntimeError("Not connected to database")
        
        channel = f'new_message_{agent_id}'
        await self.connection.add_listener(channel, self._handle_notification)

    async def stop_listening_to_agent(self, agent_id: str):
        """Stop listening to a specific agent's messages"""
        if not self.connection:
            raise RuntimeError("Not connected to database")
        
        channel = f'new_message_{agent_id}'
        await self.connection.remove_listener(channel, self._handle_notification)

    def on_message(self, callback: Callable):
        """Register a callback for all messages"""
        self.callbacks['on_message'] = callback

    def on_agent_message(self, agent_id: str, callback: Callable):
        """Register a callback for specific agent messages"""
        self.callbacks[f'agent:{agent_id}'] = callback

    async def _schedule_reconnect(self):
        """Schedule a reconnection attempt"""
        await asyncio.sleep(self.reconnect_interval)
        if self.running:
            await self.connect()

    async def disconnect(self):
        """Close the connection"""
        self.running = False
        if self.connection:
            await self.connection.close()

    async def run_forever(self):
        """Keep the connection alive"""
        await self.connect()
        try:
            while self.running:
                await asyncio.sleep(1)
                
                # Send a test query to check connection health
                if self.connection:
                    try:
                        await self.connection.fetchval('SELECT 1')
                    except:
                        print("Connection lost, reconnecting...")
                        await self._schedule_reconnect()
        except KeyboardInterrupt:
            await self.disconnect()

# Usage example
async def main():
    listener = LettaMessageListener(os.environ['LETTA_PG_URI'])
    
    # Register handlers
    async def handle_message(notification):
        print(f"New message: {notification}")
        # Fetch full message from Letta API
        message_id = notification['message_id']
        full_message = await fetch_message_from_letta(message_id)
        await process_message(full_message)
    
    listener.on_message(handle_message)
    
    # Run forever
    await listener.run_forever()

if __name__ == "__main__":
    asyncio.run(main())
```

## Integration with Existing Polling

For maximum reliability, implement LISTEN/NOTIFY alongside your existing polling mechanism:

```typescript
class HybridMessageFetcher {
  private lastSequenceId: number = 0;
  private listener: LettaMessageListener;
  private pollInterval: number = 30000; // 30 seconds as fallback
  private lastPollTime: Date = new Date();

  constructor(
    private pgUri: string,
    private lettaClient: LettaClient,
    private agentId: string
  ) {
    this.listener = new LettaMessageListener(pgUri);
    this.setupListeners();
  }

  private setupListeners(): void {
    this.listener.on('message', async (notification) => {
      if (notification.agent_id === this.agentId) {
        // Update our sequence tracker
        if (notification.sequence_id > this.lastSequenceId) {
          this.lastSequenceId = notification.sequence_id;
          this.lastPollTime = new Date();
        }
        
        // Process the message
        await this.processNewMessage(notification.message_id);
      }
    });

    this.listener.on('disconnected', () => {
      console.log('LISTEN/NOTIFY disconnected, falling back to polling');
      this.startPollingFallback();
    });

    this.listener.on('connected', () => {
      console.log('LISTEN/NOTIFY connected, stopping polling');
      this.stopPollingFallback();
    });
  }

  private async pollForMessages(): Promise<void> {
    try {
      const messages = await this.lettaClient.getMessages(this.agentId, {
        after: this.lastSequenceId.toString(),
        limit: 100
      });

      for (const message of messages) {
        await this.processNewMessage(message.id);
        // Update sequence tracker
        if (message.sequence_id > this.lastSequenceId) {
          this.lastSequenceId = message.sequence_id;
        }
      }
    } catch (error) {
      console.error('Polling error:', error);
    }
  }

  async start(): Promise<void> {
    // Start LISTEN/NOTIFY
    await this.listener.connect();
    await this.listener.listenToAgent(this.agentId);
    
    // Do an initial poll to catch up
    await this.pollForMessages();
    
    // Start periodic safety polling
    this.startSafetyPolling();
  }

  private startSafetyPolling(): void {
    // Poll occasionally even when connected as a safety net
    setInterval(async () => {
      const timeSinceLastMessage = Date.now() - this.lastPollTime.getTime();
      if (timeSinceLastMessage > 60000) { // 1 minute
        console.log('Safety poll triggered');
        await this.pollForMessages();
      }
    }, 60000);
  }
}
```

## Performance Considerations

1. **Payload Size**: The notification payload is kept minimal. Fetch full message content via Letta API.

2. **Channel Naming**: Use agent-specific channels (`new_message_{agent_id}`) to reduce notification overhead.

3. **Connection Pooling**: Use a dedicated connection for LISTEN/NOTIFY, separate from your query connection pool.

4. **Notification Queue**: PostgreSQL queues notifications if the client is slow. Process notifications quickly to avoid queue buildup.

## Monitoring and Debugging

### Check Active Listeners

```sql
SELECT pid, state, query 
FROM pg_stat_activity 
WHERE query LIKE 'LISTEN%';
```

### Monitor Notification Queue Size

```sql
SELECT count(*) 
FROM pg_notification_queue();
```

### Test Notifications Manually

```sql
-- Send a test notification
SELECT pg_notify('new_message', '{"message_id": "test-123", "agent_id": "agent-456"}');
```

## Error Handling

1. **Connection Loss**: Implement automatic reconnection with exponential backoff
2. **Notification Parse Errors**: Log and continue processing other notifications
3. **Message Fetch Failures**: Implement retry logic when fetching full message content
4. **Queue Overflow**: PostgreSQL will drop old notifications if queue is full (8GB by default)

## Security Considerations

1. **Connection Security**: Use SSL/TLS for database connections
2. **Payload Validation**: Always validate notification payloads before processing
3. **Access Control**: Ensure database user has minimal required permissions:
   ```sql
   GRANT SELECT ON message TO your_app_user;
   GRANT EXECUTE ON FUNCTION pg_notify TO your_app_user;
   ```

## Testing

Test your implementation with this script:

```sql
-- Insert a test message to trigger notification
INSERT INTO message (
  id, agent_id, user_id, role, content, 
  created_at, organization_id, sequence_id
) VALUES (
  gen_random_uuid(),
  'test-agent-123',
  'test-user-456',
  'assistant',
  '{"text": "Test message"}',
  NOW(),
  'test-org-789',
  (SELECT COALESCE(MAX(sequence_id), 0) + 1 FROM message WHERE agent_id = 'test-agent-123')
);
```

## Conclusion

This PostgreSQL LISTEN/NOTIFY implementation provides:
- **Instant notifications** (typically <5ms latency)
- **Zero polling overhead** on the Letta API
- **High reliability** with automatic reconnection
- **Simple implementation** using standard PostgreSQL features

The combination of LISTEN/NOTIFY with occasional safety polling ensures you never miss messages while maintaining extremely low latency for real-time updates.