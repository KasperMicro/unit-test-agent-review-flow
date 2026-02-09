from collections.abc import AsyncIterable
from typing import Any
import sys
import subprocess
import toml
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
    """Agent that wraps the Codex CLI as a subprocess behind the Agent Framework interface.

    This agent translates incoming chat messages into Codex CLI invocations,
    writing the prompt to a temporary file (to avoid OS command-line length
    limits) and executing ``codex exec`` in a sandboxed workspace-write mode.

    Azure OpenAI configuration (API key and endpoint) is read from environment
    variables and injected into the subprocess environment.  The agent also
    patches the ``config.toml`` inside the project's ``.codex`` directory so
    that ``base_url`` always reflects the current ``AZURE_OPENAI_ENDPOINT_CODEX``
    value.

    Args:
        name: Human-readable name for the agent instance.
        description: Short description of the agent's purpose.
        scope_dir: Filesystem directory that Codex is allowed to read/write.
            The CLI is invoked with ``-C <scope_dir>`` and the temporary prompt
            file is created here.
        **kwargs: Additional keyword arguments forwarded to ``BaseAgent``.

    Example::

        agent = CodexAgent(
            name="ImplementAgent",
            scope_dir="/path/to/working/dir",
        )
        response = await agent.run("Add unit tests for utils.py")
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
        output = self._run_codex_agent(
            prompt=prompt,
        )

        response_message = ChatMessage(role=Role.ASSISTANT, contents=[Content(type="text", text=output)])

        # Notify the thread of new messages if provided
        if thread is not None:
            await self._notify_thread_of_new_messages(thread, normalized_messages, response_message)

        return AgentResponse(messages=[response_message])

    def _run_codex_agent(
        self,
        *,
        prompt: str,
    ) -> str:
        """Spawn the Codex CLI as a subprocess and return its captured output.

        The method performs the following steps:

        1. Loads Azure OpenAI credentials (``AZURE_OPENAI_API_KEY`` and
           ``AZURE_OPENAI_ENDPOINT_CODEX``) from the environment.
        2. Patches the project's ``.codex/config.toml`` so the ``azure``
           provider's ``base_url`` matches the current endpoint.
        3. Writes *prompt* to a temporary ``.md`` file inside ``self.scope_dir``
           to sidestep Windows' ~8 191-character command-line limit.
        4. Invokes ``codex exec --sandbox workspace-write -C <scope_dir>``
           instructing Codex to read and then delete the temp file.
        5. Streams ``stdout``/``stderr`` to the console while accumulating the
           full output, and cleans up the temp file on exit.

        Args:
            prompt: The full instruction text to send to Codex.

        Returns:
            The combined stdout/stderr output produced by the Codex CLI.
            If the process exits with a non-zero code, the output is prefixed
            with a ``[Codex exited with code …]`` banner.

        Raises:
            RuntimeError: If ``AZURE_OPENAI_API_KEY`` or
                ``AZURE_OPENAI_ENDPOINT_CODEX`` is not set.
        """
        # Load .env
        load_dotenv("../.env")

        azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT_CODEX")

        print(azure_endpoint)

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
        env["AZURE_OPENAI_ENDPOINT"] = azure_endpoint

        # Point CODEX_HOME to the .codex directory inside the agents folder
        # so the CLI picks up the config.toml with the Azure provider definition.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        codex_home = os.path.join(script_dir, '.codex')
        env["CODEX_HOME"] = codex_home

        # Patch base_url in config.toml from the AZURE_OPENAI_ENDPOINT_CODEX env var
        # (Codex config doesn't support env var resolution for base_url natively)
        config_path = os.path.join(codex_home, 'config.toml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = toml.load(f)
        if 'azure' in config_data.get('model_providers', {}):
            config_data['model_providers']['azure']['base_url'] = azure_endpoint
            with open(config_path, 'w', encoding='utf-8') as f:
                toml.dump(config_data, f)

        # Write prompt to a temporary file to avoid Windows command-line length limits
        # (Windows has ~8191 char limit which can truncate long prompts passed as arguments)
        import tempfile
        prompt_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.md',
            delete=False,
            encoding='utf-8',
            dir=self.scope_dir  # Create in scope dir so Codex can access it
        )
        prompt_file.write(prompt)
        prompt_file.close()
        prompt_file_path = prompt_file.name
        prompt_file_name = os.path.basename(prompt_file_path)

        # Build command - use --input-file to read prompt from file
        cmd = [
            codex_executable,

            # ---- Subcommand (required for non-interactive/piped usage) ----
            "exec",

            # ---- Sandbox: allow writes within the working directory ----
            "--sandbox", "workspace-write",

            # ---- Scope file access to dummy_app directory ----
            "-C", self.scope_dir,

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
        scope_dir="CUsersalbinlnnfltOneDrive - MicrosoftCustomerTetra pakdevops-logging-agentcloned_code", # Fix this
    )


if __name__ == "__main__":
    # Example usage
    agent = create_implementer_agent()
    response = asyncio.run(agent.run("Add a markdown file named 'greeting.md' with the text 'Hello world!'"))
    print("Agent response:")
    print(response)