WORD_LIMIT = 1000
SYSTEM = f"""Your task is to create an intelligent summary of a work session between an AI assistant and a user.

The transcript shows:
- User messages and system events (heartbeats, login events)
- Assistant's inner thoughts, actions, and tool usage
- Tool calls with their results (formatted as: tool_name(args) → result)

Create a summary that:
1. Preserves the initial task/request context
2. Progressively compresses older activities while keeping recent ones detailed (last 30% gets most detail)
3. Retains ALL key findings, tool results, and discovered information
4. Tracks current task state and what's in progress
5. Maintains chronological flow and work continuity

Structure your summary to be scannable:
- Initial context (what was requested)
- Work progression (compressed for older, detailed for recent)
- Current state (where the task stands now)

Write from the AI assistant's first-person perspective.
Focus on information needed to continue the work effectively.
Keep within {WORD_LIMIT} words.
Output ONLY the summary."""
