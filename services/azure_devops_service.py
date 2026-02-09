"""
Azure DevOps Service - Handles all communication with Azure DevOps
"""
import os
import re
import base64
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from azure.devops.connection import Connection
from azure.devops.v7_1.git import GitClient
from azure.devops.v7_1.git.models import (
    GitPullRequest,
    GitRefUpdate,
    GitPush,
    GitCommitRef,
    Change,
    ItemContent,
    WebApiTagDefinition,
)
from msrest.authentication import BasicAuthentication
import git


@dataclass
class DevOpsConfig:
    """Configuration for Azure DevOps connection"""
    org_url: str
    pat: str
    project: str
    repo_name: str


class AzureDevOpsService:
    """
    Service class for Azure DevOps operations.
    Handles repo cloning, branch creation, commits, and pull requests.
    """
    
    def __init__(self, config: DevOpsConfig):
        self.config = config
        self._connection = None
        self._git_client: Optional[GitClient] = None
        self._repo_id = None
        
    def _get_connection(self) -> Connection:
        """Get or create Azure DevOps connection"""
        if self._connection is None:
            credentials = BasicAuthentication('', self.config.pat)
            self._connection = Connection(
                base_url=self.config.org_url,
                creds=credentials
            )
        return self._connection
    
    def _get_git_client(self) -> GitClient:
        """Get or create Git client"""
        if self._git_client is None:
            connection = self._get_connection()
            self._git_client = connection.clients.get_git_client()
        return self._git_client
    
    async def get_repository_id(self) -> str:
        """Get the repository ID by name"""
        if self._repo_id:
            return self._repo_id
            
        client = self._get_git_client()
        repos = client.get_repositories(self.config.project)
        
        for repo in repos:
            if repo.name == self.config.repo_name:
                self._repo_id = repo.id
                return repo.id
                
        raise ValueError(f"Repository '{self.config.repo_name}' not found")
    
    async def clone_repository(self, target_path: str, branch: str = "main") -> str:
        """
        Clone repository to local path using Git credentials.
        
        Args:
            target_path: Local directory to clone into
            branch: Branch to clone (default: main)
            
        Returns:
            Path to cloned repository
        """
        repo_id = await self.get_repository_id()
        client = self._get_git_client()
        repo = client.get_repository(repo_id, self.config.project)
        
        # Build authenticated URL
        # Format: https://PAT@dev.azure.com/org/project/_git/repo
        clone_url = repo.remote_url
        # Handle URLs that may already have a username (e.g., https://user@dev.azure.com/...)
        import re
        auth_url = re.sub(
            r'https://([^@]+@)?',
            f'https://:{self.config.pat}@',
            clone_url
        )
        
        # Create target directory
        Path(target_path).mkdir(parents=True, exist_ok=True)
        repo_path = os.path.join(target_path, self.config.repo_name)
        
        # Clone the repository
        if os.path.exists(repo_path):
            # Pull latest if already exists - update remote URL with auth first
            local_repo = git.Repo(repo_path)
            local_repo.remotes.origin.set_url(auth_url)
            local_repo.remotes.origin.pull(branch)
            print(f"Updated existing repository at {repo_path}")
        else:
            git.Repo.clone_from(auth_url, repo_path, branch=branch)
            print(f"Cloned repository to {repo_path}")
            
        return repo_path
    
    async def create_branch(self, branch_name: str, source_branch: str = "main") -> str:
        """
        Create a new branch from source branch.
        
        Args:
            branch_name: Name of new branch
            source_branch: Branch to create from (default: main)
            
        Returns:
            Full ref name of created branch
        """
        repo_id = await self.get_repository_id()
        client = self._get_git_client()
        
        # Get source branch object ID
        refs = client.get_refs(
            repository_id=repo_id,
            project=self.config.project,
            filter=f"heads/{source_branch}"
        )
        
        if not refs:
            raise ValueError(f"Source branch '{source_branch}' not found")
        
        source_object_id = refs[0].object_id
        
        # Create new branch
        ref_update = GitRefUpdate(
            name=f"refs/heads/{branch_name}",
            old_object_id="0000000000000000000000000000000000000000",
            new_object_id=source_object_id
        )
        
        client.update_refs(
            ref_updates=[ref_update],
            repository_id=repo_id,
            project=self.config.project
        )
        
        return f"refs/heads/{branch_name}"
    
    async def push_changes(
        self,
        branch_name: str,
        file_changes: list[dict],
        commit_message: str
    ) -> str:
        """
        Push file changes to a branch.
        
        Args:
            branch_name: Target branch name
            file_changes: List of dicts with 'path', 'content', 'change_type'
            commit_message: Commit message
            
        Returns:
            Commit ID of the push
        """
        repo_id = await self.get_repository_id()
        client = self._get_git_client()
        
        # Get current branch head
        refs = client.get_refs(
            repository_id=repo_id,
            project=self.config.project,
            filter=f"heads/{branch_name}"
        )
        
        if not refs:
            raise ValueError(f"Branch '{branch_name}' not found")
        
        old_object_id = refs[0].object_id
        
        # Prepare changes
        changes = []
        for change in file_changes:
            change_type = change.get('change_type', 'edit')
            
            git_change = Change(
                change_type=change_type,
                item={'path': change['path']},
                new_content=ItemContent(
                    content=base64.b64encode(
                        change['content'].encode('utf-8')
                    ).decode('utf-8'),
                    content_type='base64Encoded'
                )
            )
            changes.append(git_change)
        
        # Create push
        push = GitPush(
            ref_updates=[
                GitRefUpdate(
                    name=f"refs/heads/{branch_name}",
                    old_object_id=old_object_id
                )
            ],
            commits=[
                GitCommitRef(
                    comment=commit_message,
                    changes=changes
                )
            ]
        )
        
        result = client.create_push(
            push=push,
            repository_id=repo_id,
            project=self.config.project
        )
        
        return result.commits[0].commit_id
    
    async def create_pull_request(
        self,
        source_branch: str,
        target_branch: str = "main",
        title: str = "Auto-generated PR",
        description: str = "",
        reviewers: list[str] = None,
        labels: list[str] = None
    ) -> dict:
        """
        Create a pull request.
        
        Args:
            source_branch: Source branch name
            target_branch: Target branch name (default: main)
            title: PR title
            description: PR description
            reviewers: List of reviewer IDs (optional)
            labels: List of label names to add (optional)
            
        Returns:
            Pull request details dict
        """
        repo_id = await self.get_repository_id()
        client = self._get_git_client()
        
        # Build PR object
        pr = GitPullRequest(
            source_ref_name=f"refs/heads/{source_branch}",
            target_ref_name=f"refs/heads/{target_branch}",
            title=title,
            description=description
        )
        
        # Add reviewers if specified
        if reviewers:
            pr.reviewers = [{"id": r} for r in reviewers]
        
        # Create the pull request
        created_pr = client.create_pull_request(
            git_pull_request_to_create=pr,
            repository_id=repo_id,
            project=self.config.project
        )
        
        # Add labels if specified
        added_labels = []
        if labels:
            added_labels = await self.add_labels_to_pull_request(
                created_pr.pull_request_id,
                labels
            )
        
        return {
            "id": created_pr.pull_request_id,
            "url": created_pr.url,
            "title": created_pr.title,
            "status": created_pr.status,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "labels": added_labels
        }
    
    async def add_labels_to_pull_request(
        self,
        pull_request_id: int,
        labels: list[str]
    ) -> list[str]:
        """
        Add labels/tags to a pull request.
        
        Args:
            pull_request_id: The PR ID
            labels: List of label names to add
            
        Returns:
            List of added label names
        """
        repo_id = await self.get_repository_id()
        client = self._get_git_client()
        
        added_labels = []
        for label_name in labels:
            label = WebApiTagDefinition(name=label_name)
            try:
                created = client.create_pull_request_label(
                    label=label,
                    repository_id=repo_id,
                    pull_request_id=pull_request_id,
                    project=self.config.project
                )
                added_labels.append(created.name)
            except Exception as e:
                print(f"Warning: Could not add label '{label_name}': {e}")
        
        return added_labels
    
    async def get_file_content(self, file_path: str, branch: str = "main") -> str:
        """
        Get content of a file from repository.
        
        Args:
            file_path: Path to file in repository
            branch: Branch name
            
        Returns:
            File content as string
        """
        repo_id = await self.get_repository_id()
        client = self._get_git_client()
        
        item = client.get_item(
            repository_id=repo_id,
            path=file_path,
            project=self.config.project,
            version_descriptor={"version": branch, "versionType": "branch"},
            include_content=True
        )
        
        return item.content
    
    async def list_files(self, path: str = "/", branch: str = "main") -> list[dict]:
        """
        List files in a directory.
        
        Args:
            path: Directory path (default: root)
            branch: Branch name
            
        Returns:
            List of file info dicts
        """
        repo_id = await self.get_repository_id()
        client = self._get_git_client()
        
        items = client.get_items(
            repository_id=repo_id,
            project=self.config.project,
            scope_path=path,
            recursion_level="Full",
            version_descriptor={"version": branch, "versionType": "branch"}
        )
        
        return [
            {
                "path": item.path,
                "is_folder": item.is_folder,
                "size": getattr(item, 'size', 0)
            }
            for item in items
        ]


# Factory function for easy instantiation
def create_devops_service_from_env() -> AzureDevOpsService:
    """Create AzureDevOpsService from environment variables"""
    from dotenv import load_dotenv
    load_dotenv()
    
    config = DevOpsConfig(
        org_url=os.getenv("AZURE_DEVOPS_ORG_URL"),
        pat=os.getenv("AZURE_DEVOPS_PAT"),
        project=os.getenv("AZURE_DEVOPS_PROJECT"),
        repo_name=os.getenv("AZURE_DEVOPS_REPO_NAME")
    )
    
    return AzureDevOpsService(config)
