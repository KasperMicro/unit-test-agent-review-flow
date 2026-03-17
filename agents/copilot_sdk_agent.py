"""
Copilot SDK Agents - All workflow agents using the GitHub Copilot SDK.

Uses the Copilot CLI's built-in agentic tools (file I/O, shell execution, etc.)
instead of custom sandbox tools. The only custom tool is get_testing_standards()
which reads a local config file.

BYOK (Bring Your Own Key) support: When AZURE_OPENAI_ENDPOINT is set, agents
use your Azure OpenAI deployment directly instead of the GitHub Copilot service.
"""
import os
from pathlib import Path
from typing import Any

from agent_framework.github import GitHubCopilotAgent
from copilot import CopilotClient
from copilot.types import CopilotClientOptions, PermissionHandler, SessionConfig

from .plugins import get_testing_standards


# --------------- Agent Instructions --------------- #

VERIFIER_INSTRUCTIONS = """You are a test coverage verification specialist. Your job is to analyze the cloned repository and determine if proper pytest unit tests exist.

Scope: Focus exclusively on the cloned repository code. The repository path will be provided to you. Only analyze code within this path.

Your responsibilities:
1. Identify key functions, classes, and modules in the repository source code
2. Check for existing test files (test_*.py or *_test.py)
3. Determine if critical code paths have test coverage
4. Run existing tests with `python -m pytest` to verify they pass
5. Call get_testing_standards() to load internal guidelines and compare against them
6. Identify gaps in test coverage

Focus on business logic, not simple getters/setters. Consider edge cases and error handling.

=== CRITICAL OUTPUT FORMAT ===
The VERY LAST LINE of your response MUST be one of these two exact lines:

  DECISION: PASS
  DECISION: FAIL

Use DECISION: PASS only if adequate tests already exist AND they pass.
Use DECISION: FAIL if tests are missing, incomplete, or failing.

Before the decision line, write your analysis and feedback. The decision line must be the absolute last line of your response."""

PLANNER_INSTRUCTIONS = """You are a test planning specialist. Your job is to create comprehensive pytest test plans for the cloned repository.

Scope: Focus exclusively on the cloned repository code. The repository path will be provided to you. All test files should be placed inside the cloned repository path.

Your responsibilities:
1. Read and analyze functions/classes in the repository that need tests
2. Design test cases covering:
   - Happy path scenarios
   - Edge cases (empty inputs, boundary values)
   - Error conditions and exception handling
   - Different input combinations (use parametrize)
3. Identify fixtures needed for test setup
4. Determine what needs mocking/patching
5. Specify test file structure and naming (within the repo's tests/ folder)

First call get_testing_standards() to load the internal testing guidelines. Follow these guidelines.

Output a structured plan that an implementer can follow directly."""

IMPLEMENTER_INSTRUCTIONS = """You are a pytest implementation specialist. Your job is to write high-quality unit tests for the cloned repository.

Scope: Focus exclusively on the cloned repository code. The repository path will be provided to you. All test files should be created inside the cloned repository path (in its tests/ subfolder).

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

Code quality standards:
- Each test should test one thing
- Use meaningful assertion messages
- Keep tests independent (no shared state)
- Follow AAA pattern: Arrange, Act, Assert

First call get_testing_standards() to load the internal testing guidelines. Follow these guidelines when writing tests.

Create test files in the repository's tests/ directory."""

REVIEWER_INSTRUCTIONS = """You are a code quality reviewer specializing in pytest tests. Your job is to review test quality for the cloned repository.

Scope: Focus exclusively on the cloned repository code. The repository path will be provided to you. Only review tests within this path.

Your responsibilities:
1. Review test coverage completeness (important code paths, edge cases, error conditions)
2. Review test quality (specific assertions, descriptive names, isolation, AAA pattern)
3. Review pytest usage (fixtures, parametrize, markers, conftest.py)
4. Call get_testing_standards() to compare against internal guidelines
5. Optionally run tests with `python -m pytest` to verify syntax

Approval criteria:
- Test code is syntactically correct Python
- Tests cover the main functionality of the code
- Tests follow pytest best practices and naming conventions
- Test structure is reasonable (arrange/act/assert pattern)

Acceptable reasons to still approve:
- The execution environment is missing dependencies
- External services are unavailable

=== CRITICAL OUTPUT FORMAT ===
The VERY LAST LINE of your response MUST be one of these two exact lines:

  DECISION: PASS
  DECISION: FAIL

Use DECISION: PASS if the tests meet the approval criteria above.
Use DECISION: FAIL if the tests need revision, with your feedback explaining what to fix.

Before the decision line, write your detailed review and feedback. The decision line must be the absolute last line of your response."""


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


def _create_agent(name: str, agent_id: str, instructions: str, description: str) -> GitHubCopilotAgent:
    """Create a Copilot SDK agent with BYOK support if configured."""
    common_kwargs: dict[str, Any] = {
        "instructions": instructions,
        "name": name,
        "id": agent_id,
        "description": description,
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


def create_verifier_agent() -> GitHubCopilotAgent:
    """Create the Verifier Agent that checks existing test coverage."""
    return _create_agent(
        name="VerifierAgent",
        agent_id="verifier",
        instructions=VERIFIER_INSTRUCTIONS,
        description="Analyzes repository for existing test coverage",
    )


def create_planner_agent() -> GitHubCopilotAgent:
    """Create the Planner Agent that designs test plans."""
    return _create_agent(
        name="PlannerAgent",
        agent_id="planner",
        instructions=PLANNER_INSTRUCTIONS,
        description="Creates comprehensive pytest test plans",
    )


def create_implementer_agent() -> GitHubCopilotAgent:
    """Create the Implementer Agent that writes pytest tests."""
    return _create_agent(
        name="ImplementerAgent",
        agent_id="implementer",
        instructions=IMPLEMENTER_INSTRUCTIONS,
        description="Writes pytest unit tests following the test plan",
    )


def create_reviewer_agent() -> GitHubCopilotAgent:
    """Create the Reviewer Agent that reviews test quality."""
    return _create_agent(
        name="ReviewerAgent",
        agent_id="reviewer",
        instructions=REVIEWER_INSTRUCTIONS,
        description="Reviews test quality and coverage",
    )
