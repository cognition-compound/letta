#!/usr/bin/env python
"""
Script to regenerate tool schemas for agents with the fixed schema generator.
This fixes the OpenAI strict mode compatibility issue where tools don't have
all parameters in the required array.

Usage:
    python scripts/regenerate_tool_schemas.py [--agent-id AGENT_ID]
    
    If no agent ID is provided, it will regenerate schemas for all agents.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import letta modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from letta.functions.functions import derive_openai_json_schema
from letta.orm import Base
from letta.services.agent_manager import AgentManager
from letta.services.tool_manager import ToolManager
from letta.services.user_manager import UserManager
from letta.schemas.user import User as PydanticUser
from letta.server.server import SyncServer
from letta.settings import model_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def regenerate_tool_schema(tool_manager: ToolManager, tool_id: str, actor: PydanticUser) -> bool:
    """Regenerate the schema for a single tool."""
    try:
        # Get the tool
        tool = tool_manager.get_tool_by_id(tool_id=tool_id, actor=actor)
        if not tool:
            print(f"  ⚠️  Tool {tool_id} not found")
            return False
            
        # Check if it's a custom tool with source code
        if not tool.source_code:
            # Core memory tools and others without source code don't need regeneration
            # Their schemas are generated dynamically
            return True
            
        print(f"  📝 Regenerating schema for tool: {tool.name}")
        
        # Regenerate the schema using the fixed generator
        try:
            new_schema = derive_openai_json_schema(tool.source_code, name=tool.name)
            
            # Update the tool's schema
            tool.json_schema = new_schema
            tool_manager.update_tool_by_id(tool_id=tool_id, tool_update=tool, actor=actor)
            
            print(f"  ✅ Updated schema for {tool.name}")
            return True
            
        except Exception as e:
            print(f"  ❌ Failed to regenerate schema for {tool.name}: {e}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error processing tool {tool_id}: {e}")
        return False


async def regenerate_agent_tool_schemas(agent_id: str, server: SyncServer) -> None:
    """Regenerate all tool schemas for a specific agent."""
    print(f"\n🔧 Processing agent: {agent_id}")
    
    # Get the default user (for permissions)
    users = server.user_manager.list_users(limit=1)
    if not users:
        print("❌ No users found in database")
        return
    actor = users[0]
    
    try:
        # Get the agent
        agent = server.agent_manager.get_agent_by_id(agent_id=agent_id, actor=actor)
        if not agent:
            print(f"❌ Agent {agent_id} not found")
            return
            
        print(f"  Agent name: {agent.name}")
        print(f"  Number of tools: {len(agent.tools)}")
        
        # Process each tool
        updated_count = 0
        for tool in agent.tools:
            if regenerate_tool_schema(server.tool_manager, tool.id, actor):
                updated_count += 1
                
        print(f"✅ Successfully updated {updated_count}/{len(agent.tools)} tool schemas for agent {agent.name}")
        
    except Exception as e:
        print(f"❌ Error processing agent {agent_id}: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Regenerate tool schemas for agents")
    parser.add_argument(
        "--agent-id",
        help="Specific agent ID to regenerate schemas for (optional)",
        default=None
    )
    parser.add_argument(
        "--db-uri",
        help="Database URI (defaults to settings)",
        default=None
    )
    args = parser.parse_args()
    
    print("🚀 Tool Schema Regeneration Script")
    print("=" * 50)
    
    # Initialize server connection
    print("📊 Connecting to database...")
    
    # Create server instance
    server = SyncServer()
    
    if args.agent_id:
        # Regenerate for specific agent
        await regenerate_agent_tool_schemas(args.agent_id, server)
    else:
        # Get all agents and regenerate for each
        print("🔍 Finding all agents...")
        
        # Get the default user
        users = server.user_manager.list_users(limit=1)
        if not users:
            print("❌ No users found in database")
            return
        actor = users[0]
        
        agents = server.agent_manager.list_agents(actor=actor)
        print(f"Found {len(agents)} agents")
        
        for agent in agents:
            await regenerate_agent_tool_schemas(agent.id, server)
    
    print("\n✨ Schema regeneration complete!")


if __name__ == "__main__":
    asyncio.run(main())