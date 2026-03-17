"""
Copilot SDK-based Agent - Uses the official agent-framework-github-copilot
integration to create a GitHubCopilotAgent that implements the Agent Framework's
BaseAgent interface natively.

This module provides a drop-in replacement for the ChatAgent-based implementer,
using the Copilot CLI's built-in agentic tools (file I/O, shell execution, etc.)
instead of the custom sandbox tools in plugins.py.

BYOK (Bring Your Own Key) support: When AZURE_OPENAI_ENDPOINT is set, the agent
uses the Azure OpenAI deployment directly instead of the GitHub Copilot service,
removing the need for GitHub authentication.
"""
import os
from pathlib import Path
from typing import Any

from agent_framework.github import GitHubCopilotAgent
from copilot import CopilotClient
from copilot.types import CopilotClientOptions, PermissionHandler, SessionConfig

from .plugins import get_testing_standards


# --------------- Instructions --------------- #

IMPLEMENTER_INSTRUCTIONS = """You are a pytest implementation specialist. Your job is to write high-quality unit tests for the cloned repository.

Scope: Focus exclusively on the cloned repository code from Azure DevOps. The repository path will be provided to you. Only write tests for code within this path — the orchestration and agent framework code are out of scope. All test files should be created inside the cloned repository path (in its tests/ subfolder).

Your responsibilities:
1. Write pytest tests following the test plan
2. Use pytest conventions:
   - test_ prefix for test functions
   - Descriptive test names (test_function_does_something_when_condition)
   - Use fixtures for setup/teardown
   - Use @pytest.mark.parametrize for multiple test cases
   - Use pytest.raises for exception testing
3. Create conftest.py for shared fixtures (inside cloned repo)
4. Use unittest.mock for mocking dependencies
5. Write clear docstrings explaining what each test verifies

Code quality standards:
- Each test should test one thing
- Use meaningful assertion messages
- Keep tests independent (no shared state)
- Follow AAA pattern: Arrange, Act, Assert

First call get_testing_standards() to load the internal testing guidelines. Follow these guidelines when writing tests.

Create test files in the repository's tests/ directory.
All file paths should be within the cloned repository workspace path."""


def _build_byok_provider() -> tuple[dict[str, Any], str] | None:
    """Build a BYOK provider config from Azure OpenAI environment variables.

    Returns a (ProviderConfig, model_name) tuple if AZURE_OPENAI_ENDPOINT is set,
    else None.

    Authentication priority:
    1. AZURE_OPENAI_API_KEY — static API key (simplest)
    2. Entra ID / DefaultAzureCredential — acquires a bearer token at startup.
       The token is static (~1 hour lifetime) and won't auto-refresh, but that
       is sufficient for a single workflow run.
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        return None

    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4.1")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    # For type "azure", base_url should be just the host — the SDK handles
    # path construction internally.
    provider: dict[str, Any] = {
        "type": "azure",
        "base_url": endpoint.rstrip("/"),
        "azure": {"api_version": api_version},
    }

    if api_key:
        provider["api_key"] = api_key
    else:
        # Acquire a static bearer token via Entra ID (DefaultAzureCredential).
        # The Copilot SDK does not auto-refresh tokens, so this is valid for
        # ~1 hour — enough for a single workflow run.
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        provider["bearer_token"] = token.token

    return provider, deployment


class _BYOKCopilotAgent(GitHubCopilotAgent):
    """GitHubCopilotAgent subclass that injects BYOK provider into sessions.

    Creates its own CopilotClient with use_logged_in_user=False so that
    no GitHub Copilot license is required — all LLM calls are routed to the
    configured Azure OpenAI (Foundry) deployment via the provider config.
    """

    def __init__(self, provider: dict[str, Any], model: str, **kwargs: Any):
        # Build a CopilotClient that skips GitHub authentication and
        # provides a custom model listing so the CLI doesn't query GitHub.
        from copilot.types import ModelInfo, ModelCapabilities, ModelSupports, ModelLimits

        client_options: CopilotClientOptions = {
            "use_logged_in_user": False,
            "on_list_models": lambda: [
                ModelInfo(
                    id=model,
                    name=model,
                    capabilities=ModelCapabilities(
                        supports=ModelSupports(vision=False, reasoning_effort=False),
                        limits=ModelLimits(max_context_window_tokens=128000),
                    ),
                )
            ],
        }
        log_level = (kwargs.get("default_options") or {}).get("log_level")
        if log_level:
            client_options["log_level"] = log_level  # type: ignore[assignment]
        client = CopilotClient(client_options)
        kwargs["client"] = client

        super().__init__(**kwargs)
        self._byok_provider = provider
        self._byok_model = model

    async def _create_session(
        self,
        streaming: bool,
        runtime_options: dict[str, Any] | None = None,
    ):
        """Override to inject BYOK provider config into session creation."""
        if not self._client:
            raise RuntimeError("GitHub Copilot client not initialized. Call start() first.")

        opts = runtime_options or {}
        config: SessionConfig = {"streaming": streaming}

        # Always set the model — use BYOK deployment name so the CLI
        # doesn't try to query GitHub for available models.
        model = opts.get("model") or self._settings["model"] or self._byok_model
        config["model"] = model  # type: ignore[typeddict-item]

        system_message = opts.get("system_message") or self._default_options.get("system_message")
        if system_message:
            config["system_message"] = system_message

        if self._tools:
            config["tools"] = self._prepare_tools(self._tools)

        permission_handler = opts.get("on_permission_request") or self._permission_handler
        if permission_handler:
            config["on_permission_request"] = permission_handler

        mcp_servers = opts.get("mcp_servers") or self._mcp_servers
        if mcp_servers:
            config["mcp_servers"] = mcp_servers

        # Set working directory to the workspace so the CLI can access files
        workspace = os.getenv("WORKSPACE_PATH", "./cloned_code")
        config["working_directory"] = str(Path(workspace).resolve())

        # Inject BYOK provider
        config["provider"] = self._byok_provider  # type: ignore[typeddict-item]

        return await self._client.create_session(config)

    async def _get_or_create_session(
        self,
        agent_session: Any,
        streaming: bool = False,
        runtime_options: dict[str, Any] | None = None,
    ):
        """Override to always create a new session instead of resuming.

        Session resume requires GitHub authentication, which isn't available
        in BYOK-only mode. Creating a fresh session each time works because
        each invocation gets the full conversation context from the workflow.
        """
        agent_session.service_session_id = None
        return await super()._get_or_create_session(
            agent_session, streaming=streaming, runtime_options=runtime_options
        )


def create_copilot_sdk_implementer() -> GitHubCopilotAgent:
    """Create an implementer agent backed by the GitHub Copilot SDK.

    Uses the Copilot CLI's built-in tools for file I/O and shell execution,
    File operations are scoped to the workspace via the session's
    working_directory setting. The SDK's built-in PermissionHandler.approve_all
    is used since the working directory already constrains file access.

    The only custom tool retained is get_testing_standards(), which reads a
    hardcoded project config file with no user-influenced paths.

    When AZURE_OPENAI_ENDPOINT is set, uses BYOK to route requests to your
    Azure OpenAI deployment instead of the GitHub Copilot service.

    Environment variables:
    - AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint (enables BYOK)
    - AZURE_OPENAI_DEPLOYMENT_NAME: Model deployment name (default: gpt-4.1)
    - AZURE_OPENAI_API_VERSION: API version (default: 2024-10-21)
    - AZURE_OPENAI_API_KEY: API key (if not set, uses Entra ID bearer token via DefaultAzureCredential)
    - WORKSPACE_PATH: Allowed workspace directory (default: ./cloned_code)
    """
    common_kwargs: dict[str, Any] = {
        "instructions": IMPLEMENTER_INSTRUCTIONS,
        "name": "CopilotSDKImplementer",
        "id": "copilotsdkimplementer",
        "description": "Copilot SDK-based agent for implementing pytest tests",
        "tools": [get_testing_standards],
        "default_options": {
            "log_level": "info",
            "timeout": 300,
            "on_permission_request": PermissionHandler.approve_all,
        },
    }

    byok_result = _build_byok_provider()
    if byok_result:
        provider, model = byok_result
        return _BYOKCopilotAgent(provider=provider, model=model, **common_kwargs)

    return GitHubCopilotAgent(**common_kwargs)
