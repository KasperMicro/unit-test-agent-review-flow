"""
Agent Definitions for Unit Test Generation using Microsoft Agent Framework
"""
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

import asyncio
from collections.abc import AsyncIterable
from typing import Any
import sys
import subprocess
from dotenv import load_dotenv

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Role,
    Content,
)

from .plugins import FILE_TOOLS, PYTEST_TOOLS
from .quality_evaluation import VerifierOutput, ReviewerOutput


def create_chat_client() -> AzureOpenAIChatClient:
    """Create and configure an Azure OpenAI chat client"""
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    
    # Note: API version 2024-08-01-preview or later required for structured outputs
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    
    if api_key:
        return AzureOpenAIChatClient(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            api_key=api_key,
            api_version=api_version
        )
    else:
        return AzureOpenAIChatClient(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            credential=DefaultAzureCredential(),
            api_version=api_version
        )


def create_verifier_agent() -> ChatAgent:
    """
    Create the Verifier Agent responsible for:
    - Checking if pytest tests exist for key code
    - Analyzing test coverage
    - Determining if tests are sufficient
    """
    return ChatAgent(
        chat_client=create_chat_client(),
        name="VerifierAgent",
        instructions="""You are a test coverage verification specialist. Your job is to analyze a CLONED REPOSITORY and determine if proper pytest unit tests exist.

IMPORTANT: You are ONLY analyzing the cloned repository code that was cloned from Azure DevOps. 
The repository path will be provided to you. DO NOT analyze any code outside this path.
DO NOT look at or create tests for the orchestration/agent framework code itself.

Your responsibilities:
1. Identify key functions, classes, and modules in the CLONED REPOSITORY source code
2. Check for existing test files (test_*.py or *_test.py) within the cloned repo
3. Determine if critical code paths have test coverage
4. Compare against internal testing guidelines and best practices
5. Identify gaps in test coverage

When analyzing:
- Use list_local_files to find source code and test files IN THE CLONED REPO ONLY
- Use read_local_file to examine code and existing tests IN THE CLONED REPO ONLY
- Use run_pytest to verify existing tests pass
- Use get_testing_standards to load the internal testing guidelines and compare against them
- Focus on business logic of the CLONED REPO, not simple getters/setters
- Consider edge cases and error handling paths

Provide a clear analysis including:
- What tests exist and whether they pass
- What functions/classes need test coverage
- Overall assessment of whether the test suite is adequate

Be thorough but practical - not every line needs a test.""",
        tools=FILE_TOOLS + PYTEST_TOOLS,
        default_options={'response_format': VerifierOutput}
    )


def create_planner_agent() -> ChatAgent:
    """
    Create the Planner Agent responsible for:
    - Creating detailed test plans
    - Identifying test cases for each function
    - Planning fixtures and mocks needed
    """
    return ChatAgent(
        chat_client=create_chat_client(),
        name="PlannerAgent",
        instructions="""You are a test planning specialist. Your job is to create comprehensive pytest test plans for the CLONED REPOSITORY.

IMPORTANT: You are ONLY planning tests for the cloned repository code that was cloned from Azure DevOps.
The repository path will be provided to you. DO NOT plan tests for any code outside this path.
DO NOT plan tests for the orchestration/agent framework code itself.
ALL test files must be created INSIDE the cloned repository path.

Your responsibilities:
1. Analyze functions/classes in the CLONED REPO that need tests
2. Design test cases covering:
   - Happy path scenarios
   - Edge cases (empty inputs, boundary values)
   - Error conditions and exception handling
   - Different input combinations (use parametrize)
3. Identify fixtures needed for test setup
4. Determine what needs mocking/patching
5. Specify test file structure and naming (within cloned repo's tests/ folder)

Your test plans should be:
- Specific and actionable
- Following pytest best practices
- Include expected assertions
- Consider test isolation

IMPORTANT: First call get_testing_standards() to load the internal testing guidelines.
Your test plan MUST follow these guidelines.

Output a structured plan that an implementer can follow directly. The plan should not be longer then 400 words but clearly give an actional plan.
Remember: All paths should be within the cloned repository workspace.""",
        tools=FILE_TOOLS + PYTEST_TOOLS
    )


def create_reviewer_agent() -> ChatAgent:
    """
    Create the Reviewer Agent responsible for:
    - Reviewing test quality
    - Checking edge case coverage
    - Ensuring pytest best practices
    """
    return ChatAgent(
        chat_client=create_chat_client(),
        name="ReviewerAgent",
        instructions="""You are a code quality reviewer specializing in pytest tests. Your job is to review and improve test quality for the CLONED REPOSITORY.

IMPORTANT: You are ONLY reviewing tests for the cloned repository code that was cloned from Azure DevOps.
The repository path will be provided to you. DO NOT review or modify any code outside this path.
DO NOT review or modify the orchestration/agent framework code itself.
ALL test files must be within the cloned repository path.

Your responsibilities:
1. Review test coverage completeness:
   - Are all important code paths in the CLONED REPO tested?
   - Are edge cases covered?
   - Are error conditions handled?

2. Review test quality:
   - Are assertions specific and meaningful?
   - Are test names descriptive?
   - Is the test isolated (no side effects)?
   - Is the arrange/act/assert pattern followed?

3. Review pytest usage:
   - Proper use of fixtures
   - Effective use of parametrize
   - Appropriate markers (skip, xfail, etc.)
   - conftest.py organization

4. Compare against internal guidelines:
   - FIRST call get_testing_standards() to load guidelines
   - Does the code follow these testing standards?
   - Are best practices being followed?

5. Optionally run tests if you want to verify syntax:
   - Use run_pytest to execute tests
   - NOTE: Test execution failures due to missing dependencies or environment issues should NOT block approval

APPROVAL CRITERIA (set approved=true if these are met):
- Test code is syntactically correct Python
- Tests cover the main functionality of the code
- Tests follow pytest best practices and naming conventions
- Test structure is reasonable (arrange/act/assert pattern)

DO NOT reject tests just because:
- The execution environment is missing dependencies
- External services are unavailable
- The CI/CD pipeline hasn't been configured yet

This is a proof-of-concept environment. Focus on CODE QUALITY, not execution results.

Use read_local_file to review tests and write_local_file to make minor improvements.
REMEMBER: All file paths must be within the cloned repository workspace path.""",
        tools=FILE_TOOLS + PYTEST_TOOLS,
        default_options={'response_format': ReviewerOutput}
    )


# Implement agent

class ImplementAgent(BaseAgent):
    """A simple custom agent that echoes user messages with a prefix.

    This demonstrates how to create a fully custom agent by extending BaseAgent
    and implementing the required run() and run_stream() methods.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the ImplementAgent.

        Args:
            name: The name of the agent.
            description: The description of the agent.
            **kwargs: Additional keyword arguments passed to BaseAgent.
        """
        super().__init__(
            name=name,
            description=description,
            **kwargs,
        )

    def _normalize_messages(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None,
    ) -> list[ChatMessage]:
        """Normalize input messages to a list of ChatMessage objects.

        Args:
            messages: The message(s) to normalize.

        Returns:
            A list of ChatMessage objects.
        """
        if messages is None:
            return []
        if isinstance(messages, str):
            return [ChatMessage(role=Role.USER, contents=[Content(type="text", text=messages)])]
        if isinstance(messages, ChatMessage):
            return [messages]
        if isinstance(messages, list):
            result = []
            for msg in messages:
                if isinstance(msg, str):
                    result.append(ChatMessage(role=Role.USER, contents=[Content(type="text", text=msg)]))
                else:
                    result.append(msg)
            return result
        return []

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Execute the agent and return a complete response.

        Args:
            messages: The message(s) to process.
            thread: The conversation thread (optional).
            **kwargs: Additional keyword arguments.

        Returns:
            An AgentResponse containing the agent's reply.
        """
        # Normalize input messages to a list
        normalized_messages = self._normalize_messages(messages)

        if not normalized_messages:
            prompt = ""
        else:
            # Get the last user message as the prompt
            last_message = normalized_messages[-1]
            prompt = last_message.text if last_message.text else "[No text provided]"

        #print(f"PROMPT: {prompt}")

        prompt = "DONT ASK FOLLOWUP QUESTIONS. IMPLEMENT THE PLAN " + prompt

        # Run Codex agent and get the output
        deployment_name = kwargs.get("deployment_name", "gpt-5.2-codex")
        scope_dir = "cloned_code"
        output = self._run_codex_agent(
            deployment_name=deployment_name,
            prompt=prompt,
            scope_dir=scope_dir,
        )

        response_message = ChatMessage(role=Role.ASSISTANT, contents=[Content(type="text", text=output)])

        # Notify the thread of new messages if provided
        if thread is not None:
            await self._notify_thread_of_new_messages(thread, normalized_messages, response_message)

        return AgentResponse(messages=[response_message])

    def _run_codex_agent(
        self,
        *,
        deployment_name: str,
        prompt: str,
        scope_dir: str = "cloned_code",
    ) -> str:
        """
        Run Codex CLI with Azure OpenAI configuration overridden per invocation.
        Compatible with Codex CLI versions that do NOT support --provider / --model flags.

        Returns:
            The output from the Codex CLI as a string.
        """
        # Load .env
        load_dotenv("../.env")

        azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT_CODEX")

        if not azure_api_key:
            raise RuntimeError("AZURE_OPENAI_API_KEY is not set")
        if not azure_endpoint:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT_CODEX is not set")

        # Windows: npm CLIs use .cmd
        codex_executable = "codex.cmd" if sys.platform == "win32" else "codex"

        # Ensure npm global bin is on PATH (Windows safety)
        env = os.environ.copy()
        if sys.platform == "win32":
            npm_bin = os.path.expandvars(r"%APPDATA%\npm")
            if npm_bin not in env["PATH"]:
                env["PATH"] += ";" + npm_bin

        # Ensure Azure env vars are in the subprocess environment
        env["AZURE_OPENAI_API_KEY"] = azure_api_key
        env["AZURE_OPENAI_ENDPOINT_CODEX"] = azure_endpoint

        # Write prompt to a temporary file to avoid Windows command-line length limits
        # (Windows has ~8191 char limit which can truncate long prompts passed as arguments)
        import tempfile
        prompt_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.md',
            delete=False,
            encoding='utf-8',
            dir=scope_dir  # Create in scope dir so Codex can access it
        )
        prompt_file.write(prompt)
        prompt_file.close()
        prompt_file_path = prompt_file.name
        prompt_file_name = os.path.basename(prompt_file_path)

        # Build command - use --input-file to read prompt from file
        cmd = [
            codex_executable,

            # ---- Per-command config overrides ----
            "-c", "model_provider=azure",
            "-c", f"model={deployment_name}",

            "-c", f"model_providers.azure.base_url={azure_endpoint}",
            "-c", "model_providers.azure.env_key=AZURE_OPENAI_API_KEY",
            "-c", "model_providers.azure.wire_api=responses",

            # ---- Subcommand ----
            "exec",

            # ---- Enable file write access ----
            # NOTE: On Windows, -s workspace-write and --full-auto may not work reliably
            # due to WSL sandboxing constraints. Using bypass flag instead.
            "--dangerously-bypass-approvals-and-sandbox",

            # ---- Scope file access to dummy_app directory ----
            "-C", scope_dir,

            # ---- Prompt: read instructions from file ----
            f"Read the instructions from the file '{prompt_file_name}' and execute them. Delete the file when done.",
        ]

        print("Running command:")
        # Print command without the full prompt content for cleaner logs
        print(" ".join(cmd))
        print(f"Prompt length: {len(prompt)} characters")
        print(f"Prompt saved to: {prompt_file_path}")
        print(f"Prompt preview (first 500 chars): {prompt[:500]}...")
        print("-" * 60)

        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8"
            )

            # Capture output
            output_lines = []
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="")
                output_lines.append(line)

            proc.wait()

            output = "".join(output_lines)
            if proc.returncode != 0:
                output = f"[Codex exited with code {proc.returncode}]\n{output}"
        finally:
            # Clean up the temporary prompt file if Codex didn't delete it
            try:
                if os.path.exists(prompt_file_path):
                    os.unlink(prompt_file_path)
            except OSError:
                pass

        return output


def create_implementer_agent() -> ChatAgent:
    """
    Coding agent responsible for implementing pytest tests based on the test plan and review feedback.
    """
    return ImplementAgent(
        name="ImplementAgent",
        description="An agent that implements pytest tests based on the test plan and review feedback.",
    )