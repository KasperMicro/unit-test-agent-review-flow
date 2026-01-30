"""
Agents package
"""
from .agent_definitions import (
    create_chat_client,
    create_devops_agent,
    create_code_analyzer_agent,
    create_logging_agent,
    create_orchestrator_agent
)
from .plugins import (
    DEVOPS_TOOLS,
    CODE_ANALYSIS_TOOLS,
    LOGGING_TOOLS,
    clone_repository,
    create_feature_branch,
    push_file_changes,
    create_pull_request,
    list_repository_files,
    get_file_content,
    read_local_file,
    write_local_file,
    list_local_files,
    get_logging_standards,
)

__all__ = [
    'create_chat_client',
    'create_devops_agent',
    'create_code_analyzer_agent',
    'create_logging_agent',
    'create_orchestrator_agent',
    'DEVOPS_TOOLS',
    'CODE_ANALYSIS_TOOLS',
    'LOGGING_TOOLS',
    'clone_repository',
    'create_feature_branch',
    'push_file_changes',
    'create_pull_request',
    'list_repository_files',
    'get_file_content',
    'read_local_file',
    'write_local_file',
    'list_local_files',
    'get_logging_standards',
]
