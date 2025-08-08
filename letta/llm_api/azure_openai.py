from collections import defaultdict

import requests
from openai import AzureOpenAI

from letta.llm_api.openai import prepare_openai_payload
from letta.schemas.llm_config import LLMConfig
from letta.schemas.openai.chat_completion_response import ChatCompletionResponse
from letta.schemas.openai.chat_completions import ChatCompletionRequest
from letta.settings import ModelSettings


def get_azure_chat_completions_endpoint(base_url: str, model: str, api_version: str):
    return f"{base_url}/openai/deployments/{model}/chat/completions?api-version={api_version}"


def get_azure_embeddings_endpoint(base_url: str, model: str, api_version: str):
    return f"{base_url}/openai/deployments/{model}/embeddings?api-version={api_version}"


def get_azure_model_list_endpoint(base_url: str, api_version: str):
    return f"{base_url}/openai/models?api-version={api_version}"


def get_azure_deployment_list_endpoint(base_url: str):
    # Please note that it has to be 2023-03-15-preview
    # That's the only api version that works with this deployments endpoint
    # TODO: Use the Azure Client library here instead
    return f"{base_url}/openai/deployments?api-version=2023-03-15-preview"


def azure_openai_get_deployed_model_list(base_url: str, api_key: str, api_version: str) -> list:
    """https://learn.microsoft.com/en-us/rest/api/azureopenai/models/list?view=rest-azureopenai-2023-05-15&tabs=HTTP"""

    client = AzureOpenAI(api_key=api_key, api_version=api_version, azure_endpoint=base_url)

    try:
        models_list = client.models.list()
    except Exception:
        return []

    all_available_models = [model.to_dict() for model in models_list.data]

    # https://xxx.openai.azure.com/openai/models?api-version=xxx
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["api-key"] = f"{api_key}"

    # 2. Get all the deployed models
    url = get_azure_deployment_list_endpoint(base_url)
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to retrieve model list: {e}")

    deployed_models = response.json().get("data", [])
    deployed_model_names = set([m["id"] for m in deployed_models])

    # 3. Only return the models in available models if they have been deployed
    deployed_models = [m for m in all_available_models if m["id"] in deployed_model_names]

    # 4. Remove redundant deployments, only include the ones with the latest deployment
    # Create a dictionary to store the latest model for each ID
    latest_models = defaultdict()

    # Iterate through the models and update the dictionary with the most recent model
    for model in deployed_models:
        model_id = model["id"]
        updated_at = model["created_at"]

        # If the model ID is new or the current model has a more recent created_at, update the dictionary
        if model_id not in latest_models or updated_at > latest_models[model_id]["created_at"]:
            latest_models[model_id] = model

    # Extract the unique models
    return list(latest_models.values())


def azure_openai_get_chat_completion_model_list(base_url: str, api_key: str, api_version: str) -> list:
    model_list = azure_openai_get_deployed_model_list(base_url, api_key, api_version)
    # Extract models that support text generation
    model_options = [m for m in model_list if m.get("capabilities").get("chat_completion") == True]
    return model_options


def azure_openai_get_embeddings_model_list(base_url: str, api_key: str, api_version: str, require_embedding_in_name: bool = True) -> list:
    def valid_embedding_model(m: dict):
        valid_name = True
        if require_embedding_in_name:
            valid_name = "embedding" in m["id"]

        return m.get("capabilities").get("embeddings") == True and valid_name

    model_list = azure_openai_get_deployed_model_list(base_url, api_key, api_version)
    # Extract models that support embeddings

    model_options = [m for m in model_list if valid_embedding_model(m)]

    return model_options


def prepare_azure_openai_payload(chat_completion_request: ChatCompletionRequest):
    """Prepare payload for Azure OpenAI API request.
    
    Azure OpenAI currently uses Chat Completions API format, so we use
    the original payload format instead of the Responses API format.
    """
    import os
    from letta.llm_api.openai_client import supports_parallel_tool_calling
    
    data = chat_completion_request.model_dump(exclude_none=True)

    # add check otherwise will cause error: "Invalid value for 'parallel_tool_calls': 'parallel_tool_calls' is only allowed when 'tools' are specified."
    if chat_completion_request.tools is not None:
        # Enable parallel tool calls based on environment variable
        enable_parallel = os.getenv("LETTA_ENABLE_PARALLEL_TOOL_CALLS", "true").lower() == "true"
        data["parallel_tool_calls"] = enable_parallel

    # If functions == None, strip from the payload
    if "functions" in data and data["functions"] is None:
        data.pop("functions")
        data.pop("function_call", None)  # extra safe,  should exist always (default="auto")

    if "tools" in data and data["tools"] is None:
        data.pop("tools")
        data.pop("tool_choice", None)  # extra safe,  should exist always (default="auto")

    if not supports_parallel_tool_calling(chat_completion_request.model):
        data.pop("parallel_tool_calls", None)

    return data


def azure_openai_chat_completions_request(
    model_settings: ModelSettings, llm_config: LLMConfig, chat_completion_request: ChatCompletionRequest
) -> ChatCompletionResponse:
    """https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#chat-completions
    
    Note: Azure OpenAI currently uses Chat Completions API format, not Responses API.
    """

    assert model_settings.azure_api_key is not None, "Missing required api key field when calling Azure OpenAI"
    assert model_settings.azure_api_version is not None, "Missing required api version field when calling Azure OpenAI"
    assert model_settings.azure_base_url is not None, "Missing required base url field when calling Azure OpenAI"

    # Use Azure-specific payload preparation to maintain Chat Completions format
    data = prepare_azure_openai_payload(chat_completion_request)
    client = AzureOpenAI(
        api_key=model_settings.azure_api_key, api_version=model_settings.azure_api_version, azure_endpoint=model_settings.azure_base_url
    )
    chat_completion = client.chat.completions.create(**data)

    return ChatCompletionResponse(**chat_completion.model_dump())
