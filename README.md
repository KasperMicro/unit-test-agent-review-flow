# Agent Orchestration for Azure DevOps Unit Test Generation

This project provides a multi-agent orchestration system using Microsoft's **Semantic Kernel Agent Framework** to automatically generate comprehensive pytest unit tests for code repositories hosted in Azure DevOps.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATION WORKFLOW                         │
│     (Clone → Verify → Plan → Implement → Review → PR)           │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   Verifier    │ │    Planner    │ │  Implementer  │ │   Reviewer    │
│    Agent      │ │    Agent      │ │    Agent      │ │    Agent      │
│               │ │               │ │               │ │               │
│ • Check tests │ │ • Plan tests  │ │ • Write tests │ │ • Review code │
│ • Run pytest  │ │ • Prioritize  │ │ • Use pytest  │ │ • Run pytest  │
│ • Find gaps   │ │ • Identify    │ │ • Use mocking │ │ • Approve/fix │
└───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘
        │                                                   │
        ▼                                                   ▼
┌───────────────────────────────────────────────────────────────┐
│                    Azure DevOps REST API                       │
│    • Git Repositories  • Pull Requests  • Branches            │
└───────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **Python 3.10+**
2. **Azure DevOps** account with:
   - Personal Access Token (PAT) with `Code (Read & Write)` scope
   - Access to target repository
3. **Azure OpenAI** service (or managed identity authentication)
4. **Git** installed locally

## Setup

### 1. Install Dependencies

```bash
cd AgentOrchestration
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
# Azure DevOps
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-org
AZURE_DEVOPS_PAT=your-personal-access-token
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_REPO_NAME=your-repo
AZURE_DEVOPS_DEFAULT_BRANCH=main

# Azure OpenAI (managed identity - no API key required)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4

# Workspace
WORKSPACE_PATH=./workspace

# Optional: PR labels
PR_LABELS=auto-generated,unit-tests
```

### 3. Create PAT in Azure DevOps

1. Go to Azure DevOps → User Settings → Personal Access Tokens
2. Click "New Token"
3. Set scopes:
   - **Code**: Read & Write
   - **Pull Request Threads**: Read & Write
4. Copy the token to your `.env` file

## Usage

### Run the Workflow

```bash
python main.py
```

### With Custom Options

```bash
python main.py --branch develop --workspace ./my-workspace --labels "unit-tests" "auto-generated"
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--branch` | Target branch to clone and PR against | `main` (or from env) |
| `--workspace` | Local workspace path for cloned code | From env |
| `--labels` | Labels to add to the PR | From env |

## Workflow Steps

1. **Clone**: Downloads repository from Azure DevOps
2. **Verify**: Verifier agent checks existing test coverage and runs pytest
3. **Plan**: Planner agent creates a prioritized test plan
4. **Implement**: Implementer agent writes pytest unit tests
5. **Review**: Reviewer agent validates tests and runs pytest
6. **PR**: Creates pull request with all changes

## Customizing Testing Standards

Edit `config/testing_standards.md` to define your organization's pytest requirements:

- Test naming conventions
- AAA pattern usage
- Fixture guidelines
- Mocking best practices
- Coverage requirements

## Project Structure

```
AgentOrchestration/
├── main.py                 # Entry point
├── orchestration.py        # Orchestration workflow
├── requirements.txt        # Dependencies
├── .env.example           # Environment template
├── agents/
│   ├── __init__.py
│   ├── agent_definitions.py  # Agent configurations (Verifier, Planner, Implementer, Reviewer)
│   └── plugins.py           # Agent tools (file ops, pytest)
├── services/
│   ├── __init__.py
│   └── azure_devops_service.py  # DevOps API wrapper (clone, branch, PR)
├── config/
│   └── testing_standards.md    # Pytest best practices
└── workspace/              # Cloned repos go here
```

## Agents

### Verifier Agent
Analyzes the codebase to identify existing tests and coverage gaps. Runs pytest to understand current test status.

### Planner Agent
Creates a prioritized test plan based on code complexity, criticality, and missing coverage.

### Implementer Agent
Writes pytest unit tests following the testing standards. Uses fixtures, parametrize, and mocking appropriately.

### Reviewer Agent
Reviews implemented tests, runs pytest to verify they pass, and suggests improvements.

## Azure DevOps API Reference

### Key Endpoints Used

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Get Repos | GET | `/_apis/git/repositories` |
| Clone URL | GET | `/_apis/git/repositories/{id}` |
| Create Branch | POST | `/_apis/git/repositories/{id}/refs` |
| Push Changes | POST | `/_apis/git/repositories/{id}/pushes` |
| Create PR | POST | `/_apis/git/repositories/{id}/pullrequests` |

### Authentication

All requests use Basic Authentication with PAT:
```
Authorization: Basic base64(":PAT")
```

## Troubleshooting

### "Repository not found"
- Verify `AZURE_DEVOPS_REPO_NAME` matches exactly
- Check PAT has read access to the project

### "Branch creation failed"
- Ensure PAT has write access
- Verify source branch exists

### "PR creation failed"
- Check if PR already exists for the branch
- Verify target branch exists

### "Pytest not found"
- Ensure pytest is installed in the target repository
- The agents may add pytest to requirements.txt

## Extending the Solution

### Add New Agents

1. Create agent definition in `agents/agent_definitions.py`
2. Add plugins in `agents/plugins.py`
3. Update `orchestration.py` workflow

### Custom Plugins

```python
from semantic_kernel.functions import kernel_function

class MyPlugin:
    @kernel_function(name="my_function", description="Does something")
    def my_function(self, param: str) -> str:
        return f"Result: {param}"
```

## License

MIT License
