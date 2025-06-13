from letta import system
from letta.schemas.enums import MessageRole
from letta.schemas.letta_message_content import TextContent, ImageContent, LettaMessageContentUnion
from letta.schemas.message import Message, MessageCreate


def convert_message_creates_to_messages(
    message_creates: list[MessageCreate],
    agent_id: str,
    wrap_user_message: bool = True,
    wrap_system_message: bool = True,
) -> list[Message]:
    return [
        _convert_message_create_to_message(
            message_create=create,
            agent_id=agent_id,
            wrap_user_message=wrap_user_message,
            wrap_system_message=wrap_system_message,
        )
        for create in message_creates
    ]


def _convert_message_create_to_message(
    message_create: MessageCreate,
    agent_id: str,
    wrap_user_message: bool = True,
    wrap_system_message: bool = True,
) -> Message:
    """Converts a MessageCreate object into a Message object, applying wrapping if needed."""
    # TODO: This seems like extra boilerplate with little benefit
    assert isinstance(message_create, MessageCreate)

    # Handle different content types
    if isinstance(message_create.content, str):
        # Legacy string content - convert to TextContent and apply wrapping
        message_content = message_create.content

        # Apply wrapping if needed
        if message_create.role not in {MessageRole.user, MessageRole.system}:
            raise ValueError(f"Invalid message role: {message_create.role}")
        elif message_create.role == MessageRole.user and wrap_user_message:
            message_content = system.package_user_message(user_message=message_content)
        elif message_create.role == MessageRole.system and wrap_system_message:
            message_content = system.package_system_message(system_message=message_content)

        final_content = [TextContent(text=message_content)] if message_content else []

    elif message_create.content and len(message_create.content) > 0:
        # Multimodal content - preserve all content types
        if message_create.role not in {MessageRole.user, MessageRole.system}:
            raise ValueError(f"Invalid message role: {message_create.role}")

        # For multimodal content, we need to handle wrapping carefully
        # Only wrap text content, preserve image content as-is
        final_content = []
        for content_item in message_create.content:
            if isinstance(content_item, TextContent):
                text_content = content_item.text
                if message_create.role == MessageRole.user and wrap_user_message:
                    text_content = system.package_user_message(user_message=text_content)
                elif message_create.role == MessageRole.system and wrap_system_message:
                    text_content = system.package_system_message(system_message=text_content)
                final_content.append(TextContent(text=text_content))
            elif isinstance(content_item, ImageContent):
                # Preserve ImageContent as-is
                final_content.append(content_item)
            else:
                # For other content types, preserve as-is
                final_content.append(content_item)
    else:
        raise ValueError("Message content is empty or invalid")

    return Message(
        agent_id=agent_id,
        role=message_create.role,
        content=final_content,
        name=message_create.name,
        model=None,  # assigned later?
        tool_calls=None,  # irrelevant
        tool_call_id=None,
        otid=message_create.otid,
        sender_id=message_create.sender_id,
        group_id=message_create.group_id,
        batch_item_id=message_create.batch_item_id,
    )
