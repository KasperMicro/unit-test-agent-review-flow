"""
Agent Tools - Functions that agents can use for file operations and pytest.

IMPORTANT: All file operations are restricted to the workspace path (cloned code)
to prevent agents from modifying the orchestration code itself.
"""
import os
import sys
import subprocess
from pathlib import Path
from typing import Annotated
from pydantic import Field

#--------------------------------Path Validation--------------------------------#
def _get_allowed_workspace() -> Path:
    """Get the allowed workspace path from environment."""
    workspace = os.getenv("WORKSPACE_PATH", "./cloned_code")
    return Path(workspace).resolve()


def _is_path_allowed(file_path: str) -> bool:
    """Check if a path is within the allowed workspace."""
    try:
        resolved = Path(file_path).resolve()
        workspace = _get_allowed_workspace()
        return str(resolved).startswith(str(workspace))
    except Exception:
        return False


def _validate_path(file_path: str, operation: str) -> str | None:
    """Validate a path and return error message if not allowed."""
    if not _is_path_allowed(file_path):
        workspace = _get_allowed_workspace()
        return f"Error: {operation} is only allowed within the cloned code workspace: {workspace}. Path '{file_path}' is not allowed."
    return None


#--------------------------------File Tools--------------------------------#
def read_local_file(
    file_path: Annotated[str, Field(description="Full path to the local file within the cloned code workspace")]
) -> str:
    """Read a file from the cloned code workspace. Only files within the workspace path are accessible."""
    error = _validate_path(file_path, "Reading files")
    if error:
        return error
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_local_file(
    file_path: Annotated[str, Field(description="Full path to the local file within the cloned code workspace")],
    content: Annotated[str, Field(description="Content to write")]
) -> str:
    """Write content to a local file within the cloned code workspace. Cannot write outside workspace."""
    error = _validate_path(file_path, "Writing files")
    if error:
        return error
    
    try:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to: {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def list_local_files(
    directory: Annotated[str, Field(description="Directory path within the cloned code workspace")],
    pattern: Annotated[str, Field(description="File pattern (e.g., '*.py')")] = "*"
) -> str:
    """List files in a directory within the cloned code workspace. Only workspace directories are accessible."""
    error = _validate_path(directory, "Listing files")
    if error:
        return error
    
    try:
        path = Path(directory)
        files = list(path.rglob(pattern))
        # Filter out common non-code directories
        files = [f for f in files if not any(
            skip in str(f) for skip in ['.git', '__pycache__', 'node_modules', '.venv', '.pytest_cache']
        )]
        return "\n".join(str(f) for f in files[:100])
    except Exception as e:
        return f"Error listing files: {str(e)}"


#--------------------------------Pytest Tools--------------------------------#
def _ensure_pytest_installed() -> str | None:
    """Ensure pytest is installed, install if missing. Returns error message or None."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return None  # pytest is installed
    except Exception:
        pass
    
    # Try to install pytest
    try:
        print("Installing pytest...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pytest", "pytest-cov"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            return None  # Successfully installed
        return f"Failed to install pytest: {result.stderr}"
    except Exception as e:
        return f"Error installing pytest: {str(e)}"


def run_pytest(
    test_path: Annotated[str, Field(description="Path to test file or directory within the cloned code workspace")],
    verbose: Annotated[bool, Field(description="Enable verbose output")] = True
) -> str:
    """Run pytest on specified path within the cloned code workspace."""
    error = _validate_path(test_path, "Running pytest")
    if error:
        return error
    
    # Ensure pytest is installed
    install_error = _ensure_pytest_installed()
    if install_error:
        return install_error
    
    try:
        # Use sys.executable to ensure we use the same Python environment
        cmd = [sys.executable, "-m", "pytest", test_path]
        if verbose:
            cmd.append("-v")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(test_path).parent if Path(test_path).is_file() else test_path
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n\nSTDERR:\n{result.stderr}"
        
        status = "PASSED" if result.returncode == 0 else "FAILED"
        return f"Pytest {status} (exit code: {result.returncode})\n\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: Pytest timed out after 120 seconds"
    except Exception as e:
        return f"Error running pytest: {str(e)}"


def run_pytest_with_coverage(
    test_path: Annotated[str, Field(description="Path to test file or directory within the cloned code workspace")],
    source_path: Annotated[str, Field(description="Path to source code within the cloned workspace to measure coverage for")]
) -> str:
    """Run pytest with coverage report. Both paths must be within the cloned code workspace."""
    error = _validate_path(test_path, "Running pytest")
    if error:
        return error
    error = _validate_path(source_path, "Measuring coverage")
    if error:
        return error
    
    # Ensure pytest is installed
    install_error = _ensure_pytest_installed()
    if install_error:
        return install_error
    
    try:
        cmd = [
            sys.executable, "-m", "pytest",
            test_path,
            f"--cov={source_path}",
            "--cov-report=term-missing",
            "-v"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=Path(test_path).parent if Path(test_path).is_file() else test_path
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n\nSTDERR:\n{result.stderr}"
        
        return f"Coverage Report:\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: Pytest with coverage timed out after 180 seconds"
    except Exception as e:
        return f"Error running pytest with coverage: {str(e)}"

#--------------------------------Testing Standards--------------------------------#
def get_testing_standards() -> str:
    """Get the testing standards documentation for pytest best practices."""
    try:
        root = Path(__file__).parent.parent
        standards_file = root / "config" / "testing_standards.md"
        
        with open(standards_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading testing standards: {str(e)}"


#--------------------------------Tool Collections--------------------------------#
FILE_TOOLS = [
    read_local_file,
    write_local_file,
    list_local_files,
]

PYTEST_TOOLS = [
    run_pytest,
    run_pytest_with_coverage,
    get_testing_standards,
]
