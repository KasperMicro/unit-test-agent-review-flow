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

It uses the **Microsoft Agent Framework** with the **GitHub Copilot SDK** to coordinate
four specialised agents in a pipeline:

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
              │ DECISION: PASS                  │ DECISION: FAIL
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
                               │ DECISION: PASS         │ FAIL  │
                               ▼                        └───────┘
                         ┌──────────┐
                         │Create PR │
                         └──────────┘
```

The workflow is built declaratively with `WorkflowBuilder` from the Microsoft Agent
Framework. Each agent is an `AgentExecutor` backed by a `GitHubCopilotAgent`, and
routing decisions are handled by `FunctionExecutor` nodes that parse the agent's
`DECISION: PASS` or `DECISION: FAIL` marker from its text output.

---

## The Four Agents

All agents are **GitHub Copilot SDK agents** (`GitHubCopilotAgent`) running through the
Microsoft Agent Framework. They use the Copilot SDK's built-in tools for file I/O and
shell execution, plus one custom tool (`get_testing_standards`) that loads the
organisation's pytest conventions.

| Agent | Role |
|-------|------|
| **Verifier** | Scans the repo, finds existing tests, runs pytest, identifies coverage gaps. Ends with `DECISION: PASS` if tests are adequate, `DECISION: FAIL` otherwise. |
| **Planner** | Designs a comprehensive test plan (what to test, fixtures, mocks, edge cases). |
| **Implementer** | Writes the actual pytest files following the plan and testing standards. |
| **Reviewer** | Reviews the tests for quality, optionally runs them. Ends with `DECISION: PASS` to approve or `DECISION: FAIL` with feedback for revision. |

### BYOK (Bring Your Own Key)

When `AZURE_OPENAI_ENDPOINT` is set, all agents use **BYOK mode** — LLM calls are
routed directly to your Azure OpenAI deployment instead of the GitHub Copilot service.
This removes the need for GitHub Copilot authentication.

Authentication priority:
1. **`AZURE_OPENAI_API_KEY`** — static API key (simplest).
2. **`DefaultAzureCredential`** — Entra ID / managed identity (if no API key is set).

---

## Agent Tools

Agents use the **Copilot SDK's built-in tools** for file operations and shell commands
(reading, writing, listing files, running terminal commands like `python -m pytest`).
File access is scoped to the workspace via the session's `working_directory` setting.

The only custom tool is:

| Tool | Description |
|------|-------------|
| `get_testing_standards()` | Loads the organisation's testing standards from `config/testing_standards.md` |

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
│   ├── copilot_sdk_agent.py       # All agent definitions (GitHubCopilotAgent + BYOK)
│   └── plugins.py                 # Custom tool: get_testing_standards()
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
| **Azure OpenAI** | A deployed model with an endpoint URL (for BYOK mode) |

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

# Azure OpenAI (BYOK — routes LLM calls to your deployment)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_API_KEY=your-key              # Optional — omit to use DefaultAzureCredential
AZURE_OPENAI_API_VERSION=2024-10-21        # Optional — this is the default

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
| **Azure OpenAI auth errors** | If not using an API key, ensure `DefaultAzureCredential` can authenticate (e.g. `az login`). |
| **Directory locked on Windows** | VS Code's file watcher may hold a lock on `cloned_code/`. The clone logic retries and can init in-place as a fallback. |

---

## Extending the Project

### Add a new agent

1. Write a creation function in `agents/copilot_sdk_agent.py` using the `_create_agent()` factory.
2. If the agent needs new custom tools, add them in `agents/plugins.py`.
3. Wire the new agent into the workflow in `orchestration.py` using `AgentExecutor` and `WorkflowBuilder`.

### Change testing standards

Edit `config/testing_standards.md`. All agents that call `get_testing_standards()` will
pick up the changes on the next run.

### Adjust revision limits

In `orchestration.py`, change `max_revision_iterations` in `OrchestrationConfig` (default: 3).

---

## License

MIT License
