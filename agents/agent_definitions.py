"""
Agent Definitions for Unit Test Generation using Microsoft Agent Framework
"""
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

from .plugins import FILE_TOOLS, PYTEST_TOOLS
from .quality_evaluation import VerifierOutput, ReviewerOutput
from .codex_agent import CodexAgent


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


def create_implementer_agent() -> ChatAgent:
    """
    Create the Implement Agent responsible for:
    - Writing pytest test code based on the test plan
    - Creating test files in the correct structure
    - Implementing fixtures and mocks as needed
    """
    return CodexAgent(
        name = "ImplementAgent",
        description = "An agent that implements pytest tests based on the test plan and review feedback.",
    )