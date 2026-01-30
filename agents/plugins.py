"""
Agent Tools - Functions that agents can use as tools
"""
import os
from pathlib import Path
from typing import Annotated
from pydantic import Field
import git

from services.azure_devops_service import AzureDevOpsService, create_devops_service_from_env


# Global service instance for tools
_devops_service: AzureDevOpsService = None


def _get_devops_service() -> AzureDevOpsService:
    """Get or create DevOps service instance"""
    global _devops_service
    if _devops_service is None:
        _devops_service = create_devops_service_from_env()
    return _devops_service


# DevOps Tools
async def clone_repository(
    target_path: Annotated[str, Field(description="Local path to clone the repository")],
    branch: Annotated[str, Field(description="Branch name to clone")] = "main"
) -> str:
    """Clone the Azure DevOps repository to local workspace."""
    try:
        service = _get_devops_service()
        repo_path = await service.clone_repository(target_path, branch)
        return f"Successfully cloned repository to: {repo_path}"
    except Exception as e:
        return f"Error cloning repository: {str(e)}"


async def create_feature_branch(
    branch_name: Annotated[str, Field(description="Name of the new branch")],
    source_branch: Annotated[str, Field(description="Source branch to create from")] = "main"
) -> str:
    """Create a new feature branch for the logging changes."""
    try:
        service = _get_devops_service()
        ref = await service.create_branch(branch_name, source_branch)
        return f"Successfully created branch: {ref}"
    except Exception as e:
        return f"Error creating branch: {str(e)}"


async def push_file_changes(
    branch_name: Annotated[str, Field(description="Branch to push to")],
    file_path: Annotated[str, Field(description="Path of the file in repository")],
    file_content: Annotated[str, Field(description="New content of the file")],
    commit_message: Annotated[str, Field(description="Commit message")]
) -> str:
    """Push modified files to Azure DevOps."""
    try:
        service = _get_devops_service()
        changes = [{
            "path": file_path,
            "content": file_content,
            "change_type": "edit"
        }]
        commit_id = await service.push_changes(branch_name, changes, commit_message)
        return f"Successfully pushed changes. Commit ID: {commit_id}"
    except Exception as e:
        return f"Error pushing changes: {str(e)}"


async def create_pull_request(
    source_branch: Annotated[str, Field(description="Source branch with changes")],
    title: Annotated[str, Field(description="Pull request title")],
    description: Annotated[str, Field(description="Pull request description")],
    target_branch: Annotated[str, Field(description="Target branch")] = "main",
    labels: Annotated[list[str] | None, Field(description="Labels/tags to add to the PR (e.g., ['auto-generated', 'logging'])")] = None
) -> str:
    """Create a pull request for the logging changes, optionally with labels."""
    try:
        service = _get_devops_service()
        pr = await service.create_pull_request(
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=description,
            labels=labels
        )
        result = f"Successfully created PR #{pr['id']}: {pr['title']}\nURL: {pr['url']}"
        if pr.get('labels'):
            result += f"\nLabels: {', '.join(pr['labels'])}"
        return result
    except Exception as e:
        return f"Error creating pull request: {str(e)}"


async def list_repository_files(
    path: Annotated[str, Field(description="Directory path to list")] = "/",
    branch: Annotated[str, Field(description="Branch name")] = "main"
) -> str:
    """List files in the repository."""
    try:
        service = _get_devops_service()
        files = await service.list_files(path, branch)
        file_list = "\n".join([
            f"{'📁' if f['is_folder'] else '📄'} {f['path']}"
            for f in files[:50]  # Limit output
        ])
        return f"Found {len(files)} items:\n{file_list}"
    except Exception as e:
        return f"Error listing files: {str(e)}"


async def get_file_content(
    file_path: Annotated[str, Field(description="Path to the file")],
    branch: Annotated[str, Field(description="Branch name")] = "main"
) -> str:
    """Get the content of a file from the repository."""
    try:
        service = _get_devops_service()
        content = await service.get_file_content(file_path, branch)
        return content
    except Exception as e:
        return f"Error getting file content: {str(e)}"


# Code Analysis Tools
def read_local_file(
    file_path: Annotated[str, Field(description="Full path to the local file")]
) -> str:
    """Read a file from the local workspace."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_local_file(
    file_path: Annotated[str, Field(description="Full path to the local file")],
    content: Annotated[str, Field(description="Content to write")]
) -> str:
    """Write content to a local file."""
    try:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to: {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def list_local_files(
    directory: Annotated[str, Field(description="Directory path")],
    pattern: Annotated[str, Field(description="File pattern (e.g., '*.py')")] = "*"
) -> str:
    """List files in a local directory."""
    try:
        path = Path(directory)
        files = list(path.rglob(pattern))
        # Filter out common non-code directories
        files = [f for f in files if not any(
            skip in str(f) for skip in ['.git', '__pycache__', 'node_modules', '.venv']
        )]
        return "\n".join(str(f) for f in files[:100])
    except Exception as e:
        return f"Error listing files: {str(e)}"


# Logging Standards Tools
def get_logging_standards(standards_path: str = None) -> str:
    """Get the logging standards documentation that defines how logging should be implemented."""
    try:
        _standards_path = standards_path or "config/logging_standards.md"
        # Get path relative to project root
        root = Path(__file__).parent.parent
        standards_file = root / _standards_path
        
        with open(standards_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading logging standards: {str(e)}"


async def commit_and_push_local_changes(
    repo_path: Annotated[str, Field(description="Full path to the local git repository")],
    branch_name: Annotated[str, Field(description="Branch name to commit and push to")],
    commit_message: Annotated[str, Field(description="Commit message for the changes")]
) -> str:
    """Commit all local changes and push to the remote branch using git."""
    try:
        repo = git.Repo(repo_path)
        
        # Checkout or create the branch
        if branch_name in [ref.name for ref in repo.refs]:
            repo.git.checkout(branch_name)
        else:
            repo.git.checkout('-b', branch_name)
        
        # Stage all changes
        repo.git.add('--all')
        
        # Check if there are changes to commit
        if not repo.is_dirty() and not repo.untracked_files:
            return "No changes to commit"
        
        # Commit
        repo.index.commit(commit_message)
        
        # Push to remote
        origin = repo.remote('origin')
        origin.push(branch_name, set_upstream=True)
        
        # Get commit info
        commit = repo.head.commit
        changed_files = list(commit.stats.files.keys())
        
        return f"Successfully committed and pushed to '{branch_name}'.\nCommit: {commit.hexsha[:8]}\nChanged files: {', '.join(changed_files[:10])}"
    except Exception as e:
        return f"Error committing/pushing changes: {str(e)}"


# Tool collections for different agent types
DEVOPS_TOOLS = [
    clone_repository,
    create_feature_branch,
    push_file_changes,
    commit_and_push_local_changes,
    create_pull_request,
    list_repository_files,
    get_file_content,
]

CODE_ANALYSIS_TOOLS = [
    read_local_file,
    write_local_file,
    list_local_files,
]

LOGGING_TOOLS = [
    read_local_file,
    write_local_file,
    list_local_files,
    get_logging_standards,
]
