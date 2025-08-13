WORD_LIMIT = 1500
SYSTEM = f"""Your task is to extract and preserve the essential knowledge from a conversation transcript.

The transcript contains messages between conversation participants (which may be users, agents, or both) along with system events, tool usage, and discovered information.

Create a knowledge-focused summary that:
1. Extracts and preserves ALL important facts, data, insights, and discoveries
2. Maintains the context necessary to understand why information matters
3. Progressively abstracts older content to key insights while keeping recent discoveries detailed
4. Captures decisions made, conclusions reached, and understanding gained
5. Identifies the current state of knowledge and any unresolved questions

Structure your summary as:
- **Context**: The original topic, question, or task being addressed
- **Key Information & Discoveries**: Critical facts, data, findings, and insights uncovered (organized by relevance, not chronology)
- **Decisions & Conclusions**: What has been determined, decided, or concluded
- **Current Understanding**: The present state of knowledge, including what's known and what remains unclear
- **Active Work**: Any ongoing investigations or pending actions (if applicable)

Focus on WHAT was learned, discovered, and understood rather than HOW it was found.
Preserve information that would be needed to continue or reference this conversation.
Keep within {WORD_LIMIT} words.
Output ONLY the summary."""
