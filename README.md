# Agent Orchestration for Azure DevOps Logging Enhancement

This project provides a multi-agent orchestration system using Microsoft's **Semantic Kernel Agent Framework** to automatically add logging to code repositories hosted in Azure DevOps.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR AGENT                          │
│              (Coordinates the workflow)                         │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  DevOps Agent │ │ Code Analyzer │ │ Logging Agent │
│               │ │    Agent      │ │               │
│ • Clone repo  │ │ • Analyze     │ │ • Read stds   │
│ • Create PR   │ │   structure   │ │ • Add logging │
│ • Push code   │ │ • Find gaps   │ │ • Write files │
└───────────────┘ └───────────────┘ └───────────────┘
        │                                   │
        ▼                                   ▼
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
3. **Azure OpenAI** service (or OpenAI API)
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

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Workspace
WORKSPACE_PATH=C:/AgentOrchestration/workspace
```

### 3. Create PAT in Azure DevOps

1. Go to Azure DevOps → User Settings → Personal Access Tokens
2. Click "New Token"
3. Set scopes:
   - **Code**: Read & Write
   - **Pull Request Threads**: Read & Write
4. Copy the token to your `.env` file

## Usage

### Run Sequential Workflow (Recommended)

```bash
python main.py --mode sequential --branch main --patterns "*.py"
```

### Run Collaborative Agent Chat

```bash
python main.py --mode collaborative --branch develop --patterns "*.py" "*.cs"
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--mode` | `sequential` or `collaborative` | `sequential` |
| `--branch` | Target branch | `main` |
| `--patterns` | File patterns to process | `*.py` |
| `--workspace` | Local workspace path | From env |

## Workflow Steps

### Sequential Mode

1. **Clone**: Downloads repository from Azure DevOps
2. **Branch**: Creates a feature branch for changes
3. **Analyze**: Code Analyzer identifies logging opportunities
4. **Enhance**: Logging Agent adds logging statements
5. **PR**: Creates pull request with all changes

### Collaborative Mode

Agents work together in a group chat, passing information and coordinating naturally.

## Customizing Logging Standards

Edit `config/logging_standards.md` to define your organization's logging requirements:

- Log levels and when to use them
- Required logging points (function entry/exit, API calls, etc.)
- Code examples for different languages
- Structured logging format requirements

## Project Structure

```
AgentOrchestration/
├── main.py                 # Entry point
├── orchestration.py        # Orchestration logic
├── requirements.txt        # Dependencies
├── .env.example           # Environment template
├── agents/
│   ├── __init__.py
│   ├── agent_definitions.py  # Agent configurations
│   └── plugins.py           # Agent tools/functions
├── services/
│   ├── __init__.py
│   └── azure_devops_service.py  # DevOps API wrapper
├── config/
│   └── logging_standards.md    # Logging documentation
└── workspace/              # Cloned repos go here
```

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

## Extending the Solution

### Add New Agents

1. Create agent definition in `agents/agent_definitions.py`
2. Add plugins in `agents/plugins.py`
3. Register in orchestration workflow

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
