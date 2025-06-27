from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, PrivateAttr


class MessageContentType(str, Enum):
    text = "text"
    image = "image"
    tool_call = "tool_call"
    tool_return = "tool_return"
    reasoning = "reasoning"
    redacted_reasoning = "redacted_reasoning"
    omitted_reasoning = "omitted_reasoning"


class MessageContent(BaseModel):
    type: MessageContentType = Field(..., description="The type of the message.")


# -------------------------------
# Text Content
# -------------------------------


class TextContent(MessageContent):
    type: Literal[MessageContentType.text] = Field(MessageContentType.text, description="The type of the message.")
    text: str = Field(..., description="The text content of the message.")


# -------------------------------
# Image Content
# -------------------------------


class ImageSourceType(str, Enum):
    url = "url"
    base64 = "base64"
    letta = "letta"


class ImageSource(BaseModel):
    type: ImageSourceType = Field(..., description="The source type for the image.")


class UrlImage(ImageSource):
    type: Literal[ImageSourceType.url] = Field(ImageSourceType.url, description="The source type for the image.")
    url: str = Field(..., description="The URL of the image.")


class Base64Image(ImageSource):
    type: Literal[ImageSourceType.base64] = Field(ImageSourceType.base64, description="The source type for the image.")
    media_type: str = Field(..., description="The media type for the image.")
    data: str = Field(..., description="The base64 encoded image data.")
    detail: Optional[str] = Field(
        None,
        description="What level of detail to use when processing and understanding the image (low, high, or auto to let the model decide)",
    )


class LettaImage(ImageSource):
    type: Literal[ImageSourceType.letta] = Field(ImageSourceType.letta, description="The source type for the image.")
    file_id: str = Field(..., description="The unique identifier of the image file persisted in storage.")
    media_type: Optional[str] = Field(None, description="The media type for the image.")
    data: Optional[str] = Field(None, description="The base64 encoded image data.")
    detail: Optional[str] = Field(
        None,
        description="What level of detail to use when processing and understanding the image (low, high, or auto to let the model decide)",
    )


ImageSourceUnion = Annotated[Union[UrlImage, Base64Image, LettaImage], Field(discriminator="type")]


class ImageContent(MessageContent):
    type: Literal[MessageContentType.image] = Field(MessageContentType.image, description="The type of the message.")
    source: ImageSourceUnion = Field(..., description="The source of the image.")
    _detail: Optional[str] = PrivateAttr(default=None)  # Store detail for URL images
    
    def __init__(self, **data):
        """
        Initialize ImageContent with support for legacy API parameters.
        
        This constructor handles backward compatibility for the old API format that used
        'image_url' and 'detail' parameters directly, converting them to the new 'source' format.
        
        Args:
            **data: Keyword arguments that may include:
                - source: ImageSourceUnion (new format)
                - image_url: str (legacy format)
                - detail: Optional[str] (legacy format, only for URL images)
        """
        # Extract detail for URL images before processing
        detail_for_url = None
        
        # Handle legacy API with image_url and detail parameters
        if "image_url" in data and "source" not in data:
            image_url = data.pop("image_url")
            detail = data.pop("detail", None)
            
            # Determine source type based on URL format
            if image_url.startswith("data:"):
                # Parse data URL format: data:image/type;base64,data
                parts = image_url.split(",", 1)
                if len(parts) == 2:
                    header = parts[0]
                    data_content = parts[1]
                    # Extract media type from header
                    media_type = "image/jpeg"  # default
                    if ":" in header and ";" in header:
                        media_type = header.split(":")[1].split(";")[0]
                    
                    data["source"] = Base64Image(
                        type=ImageSourceType.base64,
                        media_type=media_type,
                        data=data_content,
                        detail=detail
                    )
                else:
                    # Invalid data URL format, treat as regular URL
                    data["source"] = UrlImage(
                        type=ImageSourceType.url,
                        url=image_url
                    )
                    # Store detail separately for URL images
                    detail_for_url = detail
            else:
                # HTTP/HTTPS URL
                data["source"] = UrlImage(
                    type=ImageSourceType.url, 
                    url=image_url
                )
                # Store detail separately for URL images
                detail_for_url = detail
        
        super().__init__(**data)
        
        # Set the private attribute after initialization
        if detail_for_url is not None:
            self._detail = detail_for_url
    
    @property
    def image_url(self) -> str:
        """Get the image URL from the source."""
        if isinstance(self.source, UrlImage):
            return self.source.url
        elif isinstance(self.source, Base64Image):
            return f"data:{self.source.media_type};base64,{self.source.data}"
        elif isinstance(self.source, LettaImage):
            # For LettaImage, return data URL if data is available
            if self.source.data and self.source.media_type:
                return f"data:{self.source.media_type};base64,{self.source.data}"
            else:
                # Return a placeholder URL with file_id
                return f"letta://file/{self.source.file_id}"
        else:
            raise ValueError(f"Unknown image source type: {type(self.source)}")
    
    @property
    def detail(self) -> Optional[str]:
        """Get the detail level from the source."""
        if isinstance(self.source, (Base64Image, LettaImage)):
            return self.source.detail
        elif isinstance(self.source, UrlImage):
            # For URL images, return stored detail or default to "auto"
            return self._detail if self._detail is not None else "auto"
        return None


# -------------------------------
# User Content Types
# -------------------------------


LettaUserMessageContentUnion = Annotated[
    Union[TextContent, ImageContent],
    Field(discriminator="type"),
]


def create_letta_user_message_content_union_schema():
    return {
        "oneOf": [
            {"$ref": "#/components/schemas/TextContent"},
            {"$ref": "#/components/schemas/ImageContent"},
        ],
        "discriminator": {
            "propertyName": "type",
            "mapping": {
                "text": "#/components/schemas/TextContent",
                "image": "#/components/schemas/ImageContent",
            },
        },
    }


def get_letta_user_message_content_union_str_json_schema():
    return {
        "anyOf": [
            {
                "type": "array",
                "items": {
                    "$ref": "#/components/schemas/LettaUserMessageContentUnion",
                },
            },
            {"type": "string"},
        ],
    }


# -------------------------------
# Assistant Content Types
# -------------------------------


LettaAssistantMessageContentUnion = Annotated[
    Union[TextContent],
    Field(discriminator="type"),
]


def create_letta_assistant_message_content_union_schema():
    return {
        "oneOf": [
            {"$ref": "#/components/schemas/TextContent"},
        ],
        "discriminator": {
            "propertyName": "type",
            "mapping": {
                "text": "#/components/schemas/TextContent",
            },
        },
    }


def get_letta_assistant_message_content_union_str_json_schema():
    return {
        "anyOf": [
            {
                "type": "array",
                "items": {
                    "$ref": "#/components/schemas/LettaAssistantMessageContentUnion",
                },
            },
            {"type": "string"},
        ],
    }


# -------------------------------
# Intermediate Step Content Types
# -------------------------------


class ToolCallContent(MessageContent):
    type: Literal[MessageContentType.tool_call] = Field(
        MessageContentType.tool_call, description="Indicates this content represents a tool call event."
    )
    id: str = Field(..., description="A unique identifier for this specific tool call instance.")
    name: str = Field(..., description="The name of the tool being called.")
    input: dict = Field(
        ..., description="The parameters being passed to the tool, structured as a dictionary of parameter names to values."
    )


class ToolReturnContent(MessageContent):
    type: Literal[MessageContentType.tool_return] = Field(
        MessageContentType.tool_return, description="Indicates this content represents a tool return event."
    )
    tool_call_id: str = Field(..., description="References the ID of the ToolCallContent that initiated this tool call.")
    content: str = Field(..., description="The content returned by the tool execution.")
    is_error: bool = Field(..., description="Indicates whether the tool execution resulted in an error.")


class ReasoningContent(MessageContent):
    type: Literal[MessageContentType.reasoning] = Field(
        MessageContentType.reasoning, description="Indicates this is a reasoning/intermediate step."
    )
    is_native: bool = Field(..., description="Whether the reasoning content was generated by a reasoner model that processed this step.")
    reasoning: str = Field(..., description="The intermediate reasoning or thought process content.")
    signature: Optional[str] = Field(None, description="A unique identifier for this reasoning step.")


class RedactedReasoningContent(MessageContent):
    type: Literal[MessageContentType.redacted_reasoning] = Field(
        MessageContentType.redacted_reasoning, description="Indicates this is a redacted thinking step."
    )
    data: str = Field(..., description="The redacted or filtered intermediate reasoning content.")


class OmittedReasoningContent(MessageContent):
    type: Literal[MessageContentType.omitted_reasoning] = Field(
        MessageContentType.omitted_reasoning, description="Indicates this is an omitted reasoning step."
    )
    # NOTE: dropping because we don't track this kind of information for the other reasoning types
    # tokens: int = Field(..., description="The reasoning token count for intermediate reasoning content.")


LettaMessageContentUnion = Annotated[
    Union[
        TextContent, ImageContent, ToolCallContent, ToolReturnContent, ReasoningContent, RedactedReasoningContent, OmittedReasoningContent
    ],
    Field(discriminator="type"),
]


def create_letta_message_content_union_schema():
    return {
        "oneOf": [
            {"$ref": "#/components/schemas/TextContent"},
            {"$ref": "#/components/schemas/ImageContent"},
            {"$ref": "#/components/schemas/ToolCallContent"},
            {"$ref": "#/components/schemas/ToolReturnContent"},
            {"$ref": "#/components/schemas/ReasoningContent"},
            {"$ref": "#/components/schemas/RedactedReasoningContent"},
            {"$ref": "#/components/schemas/OmittedReasoningContent"},
        ],
        "discriminator": {
            "propertyName": "type",
            "mapping": {
                "text": "#/components/schemas/TextContent",
                "image": "#/components/schemas/ImageContent",
                "tool_call": "#/components/schemas/ToolCallContent",
                "tool_return": "#/components/schemas/ToolReturnContent",  # Fixed: was incorrectly mapped to ToolCallContent
                "reasoning": "#/components/schemas/ReasoningContent",
                "redacted_reasoning": "#/components/schemas/RedactedReasoningContent",
                "omitted_reasoning": "#/components/schemas/OmittedReasoningContent",
            },
        },
    }


def get_letta_message_content_union_str_json_schema():
    return {
        "anyOf": [
            {
                "type": "array",
                "items": {
                    "$ref": "#/components/schemas/LettaMessageContentUnion",
                },
            },
            {"type": "string"},
        ],
    }
