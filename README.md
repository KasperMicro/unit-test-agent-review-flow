# Agent Orchestration — Automated Unit Test Generation for Azure DevOps

> **Disclaimer — Proof of Concept**
>
> This project is a **proof of concept** meant to serve as **inspiration** and a
> starting point for exploring multi-agent orchestration. It is not designed or
> intended for production use.
>
> The code has not undergone formal security review or thorough testing, and it may
> not cover all edge cases. If you'd like to build on this work, please make sure to
> review, adapt, and test it to meet the standards of your own environment before
> deploying it anywhere beyond local experimentation.
>
> No warranties or guarantees are provided — this is shared as-is for learning and
> exploration.

---

## What Is This?

This project demonstrates how multiple AI agents can work together to **automatically
generate pytest unit tests** for a code repository hosted in Azure DevOps.

It uses the **Microsoft Agent Framework** to coordinate four specialised agents in a
pipeline:

1. **Clone** the target repository from Azure DevOps.
2. **Verify** what tests already exist and where the gaps are.
3. **Plan** which tests to write and how.
4. **Implement** the actual pytest test code.
5. **Review** the tests for quality and correctness.
6. **Create a Pull Request** with the new tests back in Azure DevOps.

If the reviewer is not satisfied, the pipeline loops back to the planner for revisions
(up to a configurable maximum) before ultimately opening the PR.

---

## How the Workflow Operates

```
                        ┌──────────────┐
                        │    Clone     │
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │   Verifier   │
                        └──────┬───────┘
                               │
              ┌────────────────┴────────────────┐
              │ tests correct                   │ tests needed
              ▼                                 ▼
        ┌──────────┐                     ┌──────────────┐
        │ Complete │                     │   Planner    │◄──────┐
        │(no action)│                    └──────┬───────┘       │
        └──────────┘                            ▼               │
                                         ┌──────────────┐       │
                                         │ Implementer  │       │
                                         └──────┬───────┘       │
                                                ▼               │
                                         ┌──────────────┐       │
                                         │   Reviewer   │       │
                                         └──────┬───────┘       │
                                                │               │
                               ┌────────────────┴───────┐       │
                               │ approved               │ revise│
                               ▼                        └───────┘
                         ┌──────────┐
                         │Create PR │
                         └──────────┘
```

The workflow is built declaratively with `WorkflowBuilder` from the Microsoft Agent
Framework. Each agent is an `AgentExecutor` and routing decisions are handled by
`FunctionExecutor` nodes that inspect the agent's structured output (Pydantic models).

---

## The Four Agents

| Agent | Role | Tools it uses |
|-------|------|---------------|
| **Verifier** | Scans the repo, finds existing tests, runs pytest, identifies coverage gaps. Returns a structured `VerifierOutput` with a `tests_exist_and_correct` boolean. | `read_local_file`, `list_local_files`, `run_pytest`, `get_testing_standards` |
| **Planner** | Designs a comprehensive test plan (what to test, which fixtures and mocks are needed, edge cases). | `read_local_file`, `list_local_files`, `get_testing_standards` |
| **Implementer** | Writes the actual pytest files following the plan and the testing standards. Saves them into the repo's `tests/` directory. | `read_local_file`, `write_local_file`, `list_local_files`, `run_pytest`, `get_testing_standards` |
| **Reviewer** | Reviews the implemented tests for quality, runs them, and returns a structured `ReviewerOutput` with an `approved` boolean. If not approved, it provides feedback that goes back to the planner. | `read_local_file`, `write_local_file`, `list_local_files`, `run_pytest`, `run_pytest_with_coverage`, `get_testing_standards` |

All agents use **Azure OpenAI** (via the Microsoft Agent Framework's `AzureOpenAIChatClient`) and support both API key and managed-identity authentication.

---

## Agent Tools (Plugins)

Agents interact with the local file system and pytest through a set of sandboxed tool
functions defined in `agents/plugins.py`. Every file operation is restricted to the
workspace directory (the cloned repo) to prevent agents from modifying the orchestration
code itself.

### File Tools

| Tool | Description |
|------|-------------|
| `read_local_file(file_path)` | Read a file from the workspace |
| `write_local_file(file_path, content)` | Write/create a file in the workspace |
| `list_local_files(directory, pattern)` | List files matching a glob pattern |

### Pytest Tools

| Tool | Description |
|------|-------------|
| `run_pytest(test_path, verbose)` | Run pytest on a test file or directory |
| `run_pytest_with_coverage(test_path, source_path)` | Run pytest with a coverage report |
| `get_testing_standards()` | Load the organisation's testing standards from `config/testing_standards.md` |

### Path Security

- Only **relative paths** are accepted (e.g. `dummy-repo/app.py`).
- **Absolute paths** and **directory traversal** (`..`) are rejected.
- All paths are resolved against the `WORKSPACE_PATH` environment variable.

---

## Structured Agent Outputs

The Verifier and Reviewer agents return structured JSON via Pydantic models so the
workflow can make deterministic routing decisions:

```python
class VerifierOutput(BaseModel):
    tests_exist_and_correct: bool   # Are existing tests adequate?
    feedback: str                   # Summary of findings

class ReviewerOutput(BaseModel):
    approved: bool                  # Do the tests meet quality standards?
    feedback: str                   # Review notes and issues
```

These models are passed as `response_format` to the agent, guaranteeing parseable
structured output from the LLM.

---

## Azure DevOps Integration

The `AzureDevOpsService` class in `services/azure_devops_service.py` wraps the Azure
DevOps Python SDK to handle:

- **Repository discovery** — looks up the repo by name.
- **Cloning** — clones (or pulls) the repo locally using an authenticated URL.
- **Branch creation** — creates a feature branch from the target branch.
- **Pull request creation** — opens a PR with a description summarising the verifier
  and reviewer outputs, and optionally adds labels.

Authentication uses a **Personal Access Token (PAT)** with `Code (Read & Write)` and
`Pull Request Threads (Read & Write)` scopes.

---

## Testing Standards

The file `config/testing_standards.md` contains the organisation's pytest conventions.
Agents read this file at runtime (via the `get_testing_standards` tool) and follow its
rules when planning and writing tests. You can customise it to enforce your own
standards for:

- Naming conventions (`test_<function>_<scenario>`)
- AAA pattern (Arrange / Act / Assert)
- Fixture usage and `conftest.py` structure
- `@pytest.mark.parametrize` usage
- Mocking and patching guidelines
- What must vs. may be tested

---

## Project Structure

```
AgentOrchestration/
├── main.py                        # CLI entry point — parses args, runs the workflow
├── orchestration.py               # Declarative workflow definition with WorkflowBuilder
├── devui_mode.py                  # Interactive browser UI for testing agents individually
├── requirements.txt               # Python dependencies
├── agents/
│   ├── __init__.py                # Package exports
│   ├── agent_definitions.py       # Agent creation functions and system prompts
│   ├── models.py                  # VerifierOutput / ReviewerOutput Pydantic models
│   └── plugins.py                 # Sandboxed tool functions (file I/O, pytest)
├── services/
│   ├── __init__.py                # Package exports
│   └── azure_devops_service.py    # Azure DevOps SDK wrapper (clone, branch, PR)
├── config/
│   └── testing_standards.md       # Pytest best practices document
└── cloned_code/                   # Default workspace — cloned repos land here
```

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Python** | 3.10 or later |
| **Git** | Installed and available on `PATH` |
| **Azure DevOps** | An organisation, project, and repository you have access to |
| **Azure DevOps PAT** | Scopes: `Code (Read & Write)`, `Pull Request Threads (Read & Write)` |
| **Azure OpenAI** | A deployed model (e.g. GPT-4) with an endpoint URL |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a `.env` file

Create a `.env` file in the project root with the following variables:

```env
# Azure DevOps
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-org
AZURE_DEVOPS_PAT=your-personal-access-token
AZURE_DEVOPS_PROJECT=your-project-name
AZURE_DEVOPS_REPO_NAME=your-repo-name
AZURE_DEVOPS_DEFAULT_BRANCH=main

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
# AZURE_OPENAI_API_KEY=your-key        # Optional — omit to use managed identity
# AZURE_OPENAI_API_VERSION=2024-08-01-preview  # Optional — this is the default

# Workspace (where repos are cloned to)
WORKSPACE_PATH=./cloned_code

# Optional: labels added to the PR
PR_LABELS=auto-generated,unit-tests
```

### 3. Create a PAT in Azure DevOps

1. Go to **Azure DevOps → User Settings → Personal Access Tokens**.
2. Click **New Token**.
3. Select scopes: **Code** (Read & Write) and **Pull Request Threads** (Read & Write).
4. Copy the generated token into your `.env` file.

---

## Usage

### Run the full pipeline

```bash
python main.py
```

### Override settings via CLI flags

```bash
python main.py --branch develop --workspace ./my-workspace --labels "unit-tests" "auto-generated"
```

| Flag | Description | Default |
|------|-------------|---------|
| `--branch` | Branch to clone and target for the PR | `main` (or `AZURE_DEVOPS_DEFAULT_BRANCH`) |
| `--workspace` | Local directory for cloned code | `WORKSPACE_PATH` env var |
| `--labels` | Labels to attach to the PR | `PR_LABELS` env var |

### Run in DevUI mode (interactive browser UI)

```bash
python devui_mode.py
```

This starts a local web server on `http://localhost:8090` where you can interact with
each agent individually or run the full workflow step by step. Useful for debugging and
experimentation.

---

## Troubleshooting

| Problem | What to check |
|---------|---------------|
| **"Repository not found"** | Verify `AZURE_DEVOPS_REPO_NAME` matches the exact repo name in Azure DevOps. Ensure the PAT has read access. |
| **"Branch creation failed"** | Ensure the PAT has write access. Confirm the source branch exists. |
| **"PR creation failed"** | A PR for the same branch may already exist. Verify the target branch exists. |
| **"Pytest not found"** | The tool auto-installs pytest if missing. Check your Python environment has pip access. |
| **Azure OpenAI auth errors** | If not using an API key, ensure `DefaultAzureCredential` can authenticate (e.g. `az login`). |

---

## Extending the Project

### Add a new agent

1. Write a creation function in `agents/agent_definitions.py` (define system prompt, tools, and optional `response_format`).
2. If the agent needs new tools, add them in `agents/plugins.py`.
3. Wire the new agent into the workflow in `orchestration.py` using `AgentExecutor` and `WorkflowBuilder`.

### Change testing standards

Edit `config/testing_standards.md`. All agents that call `get_testing_standards()` will
pick up the changes on the next run.

### Adjust revision limits

In `orchestration.py`, change `max_revision_iterations` in `OrchestrationConfig` (default: 3).

---

## License

MIT License
