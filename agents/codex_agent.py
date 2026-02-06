from collections.abc import AsyncIterable
from typing import Any
import sys
import subprocess
from dotenv import load_dotenv
load_dotenv()
import os
import asyncio

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Role,
    Content,
    ChatAgent
)

class CodexAgent(BaseAgent):
    """A simple custom agent that echoes user messages with a prefix.

    This demonstrates how to create a fully custom agent by extending BaseAgent
    and implementing the required run() and run_stream() methods.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        scope_dir: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the CodexAgent.

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
        self.scope_dir = scope_dir

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

        prompt = "DONT ASK FOLLOWUP QUESTIONS. IMPLEMENT THE PLAN " + prompt

        # Run Codex agent and get the output
        deployment_name = kwargs.get("deployment_name", "gpt-5.2-codex")
        output = self._run_codex_agent(
            deployment_name=deployment_name,
            prompt=prompt,
            scope_dir=self.scope_dir,
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
        scope_dir: str = "CUsersalbinlnnfltOneDrive - MicrosoftCustomerTetra pakdevops-logging-agentcloned_code",
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
            "--full-auto",

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
    return CodexAgent(
        name="ImplementAgent",
        description="An agent that implements pytest tests based on the test plan and review feedback.",
        scope_dir="CUsersalbinlnnfltOneDrive - MicrosoftCustomerTetra pakdevops-logging-agentcloned_code",
    )


if __name__ == "__main__":
    # Example usage
    agent = create_implementer_agent()
    response = asyncio.run(agent.run("Add a markdown file named 'greeting.md' with the text 'Hello world!' and commit the change with message 'Add greeting file'"))
    print("Agent response:")
    print(response)