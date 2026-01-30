"""
Agent Definitions using Microsoft Agent Framework
"""
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

from .plugins import DEVOPS_TOOLS, CODE_ANALYSIS_TOOLS, LOGGING_TOOLS


def create_chat_client() -> AzureOpenAIChatClient:
    """Create and configure an Azure OpenAI chat client"""
    # Try API key first, fall back to DefaultAzureCredential
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    
    if api_key:
        return AzureOpenAIChatClient(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            api_key=api_key,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        )
    else:
        return AzureOpenAIChatClient(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            credential=DefaultAzureCredential(),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        )


def create_devops_agent() -> ChatAgent:
    """
    Create the DevOps Agent responsible for:
    - Cloning repositories
    - Creating branches
    - Pushing changes
    - Creating pull requests
    """
    return ChatAgent(
        chat_client=create_chat_client(),
        name="DevOpsAgent",
        instructions="""You are a DevOps automation agent specialized in Azure DevOps operations.

Your responsibilities:
1. Clone code repositories from Azure DevOps
2. Create feature branches for changes
3. Push modified code back to Azure DevOps
4. Create pull requests for code review

When asked to perform DevOps operations:
- Always confirm successful completion of each step
- Report any errors clearly
- Provide relevant details like branch names, commit IDs, and PR URLs

Use the available tools to interact with Azure DevOps.""",
        tools=DEVOPS_TOOLS
    )


def create_code_analyzer_agent() -> ChatAgent:
    """
    Create the Code Analyzer Agent responsible for:
    - Analyzing code structure
    - Identifying functions/methods that need logging
    - Understanding code patterns
    """
    return ChatAgent(
        chat_client=create_chat_client(),
        name="CodeAnalyzerAgent",
        instructions="""You are a code analysis expert. Your job is to analyze source code and identify:

1. Functions and methods that need logging added
2. Error handling blocks that should log exceptions
3. External API calls that need request/response logging
4. Database operations that need audit logging
5. Entry/exit points of important business logic

When analyzing code:
- Identify the programming language
- List specific functions/methods and line numbers
- Explain why logging is needed at each location
- Consider the logging standards documentation

Provide clear, structured analysis that the Logging Agent can use to add appropriate logging.""",
        tools=CODE_ANALYSIS_TOOLS
    )


def create_logging_agent() -> ChatAgent:
    """
    Create the Logging Agent responsible for:
    - Adding logging statements according to standards
    - Modifying code files with proper logging
    - Ensuring consistent logging patterns
    """
    return ChatAgent(
        chat_client=create_chat_client(),
        name="LoggingAgent",
        instructions="""You are a logging implementation specialist. Your job is to add logging to code following the organization's logging standards.

Your responsibilities:
1. Read the logging standards documentation first
2. Receive code analysis from the Code Analyzer Agent
3. Add appropriate logging statements to the code
4. Ensure logging follows the documented standards:
   - Use correct log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
   - Add structured logging with named parameters
   - Log function entry/exit at DEBUG level
   - Log external calls at INFO level
   - Log exceptions at ERROR level with stack traces

When modifying code:
- Preserve existing functionality
- Add necessary logging imports
- Use idiomatic logging patterns for the language
- Write the modified code to the local workspace

Always refer to the logging standards before making changes.""",
        tools=LOGGING_TOOLS
    )


def create_orchestrator_agent() -> ChatAgent:
    """
    Create the Orchestrator Agent that coordinates the workflow
    """
    return ChatAgent(
        chat_client=create_chat_client(),
        name="OrchestratorAgent",
        instructions="""You are the workflow orchestrator for the logging enhancement pipeline.

Your job is to coordinate the following workflow:
1. Direct the DevOps Agent to clone the target repository
2. Ask the Code Analyzer Agent to analyze the code
3. Direct the Logging Agent to add logging based on the analysis
4. Direct the DevOps Agent to create a branch, push changes, and create a PR

Workflow steps:
1. CLONE: Get the code from Azure DevOps
2. ANALYZE: Identify where logging is needed
3. ENHANCE: Add logging statements following standards
4. COMMIT: Push changes and create pull request

Coordinate between agents clearly:
- Pass relevant information between agents
- Track progress through each step
- Handle any errors gracefully
- Provide status updates

Start by asking which repository and branch to process."""
    )
