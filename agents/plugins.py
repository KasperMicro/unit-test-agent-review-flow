"""
Agent Tools - Functions that agents can use for file operations and pytest.

All file operations are restricted to the workspace path (cloned code)
to prevent agents from modifying the orchestration code itself.

Tools accept relative paths (e.g. "dummy-repo/app.py") which are resolved
against the workspace root internally.
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


def _sanitize_output(text: str) -> str:
    """Strip the absolute workspace prefix from tool output.
    
    Prevents agents from seeing (and attempting to use) absolute paths
    in pytest output, error messages, or file listings.
    Handles both forward-slash and backslash variants.
    """
    workspace = str(_get_allowed_workspace())
    # Replace both slash styles (Windows paths may appear either way)
    for prefix in (workspace + os.sep, workspace + "/", workspace + "\\", workspace):
        if prefix in text:
            text = text.replace(prefix, "")
    return text


def _resolve_relative_path(relative_path: str) -> Path:
    """Resolve a relative path against the workspace root.
    
    Only accepts relative paths like:
      - "dummy-repo/app.py"
      - "dummy-repo/tests/"
    
    Absolute paths are rejected by _validate_and_resolve.
    """
    return (_get_allowed_workspace() / relative_path).resolve()


def _is_path_allowed(file_path: str) -> bool:
    """Check if a path is within the allowed workspace."""
    try:
        resolved = _resolve_relative_path(file_path)
        workspace = _get_allowed_workspace()
        return str(resolved).startswith(str(workspace))
    except Exception:
        return False


def _validate_and_resolve(file_path: str, operation: str) -> tuple[Path | None, str | None]:
    """Validate a path and return (resolved_path, error_message).
    
    Returns the resolved absolute path if valid, or an error message if not.
    Rejects absolute paths and directory traversal attempts.
    """
    # Reject absolute paths (e.g. C:\Users\... or /mnt/data)
    if Path(file_path).is_absolute():
        print(f"[SECURITY] Rejected absolute path in {operation}: {file_path}")
        return None, f"Error: Absolute paths are not allowed. Use a relative path like 'dummy-repo/app.py'."
    
    # Reject directory traversal
    if '..' in file_path:
        print(f"[SECURITY] Rejected path traversal in {operation}: {file_path}")
        return None, f"Error: Path traversal ('..') is not allowed. Use a relative path like 'dummy-repo/app.py'."
    
    resolved = _resolve_relative_path(file_path)
    workspace = _get_allowed_workspace()
    if not str(resolved).startswith(str(workspace)):
        return None, f"Error: {operation} is only allowed within the workspace. Use a relative path like 'dummy-repo/app.py'."
    return resolved, None


#--------------------------------File Tools--------------------------------#
def read_local_file(
    file_path: Annotated[str, Field(description="Relative path to the file within the workspace, e.g. 'dummy-repo/app.py'")]
) -> str:
    """Read a file from the workspace. Use relative paths like 'dummy-repo/app.py'."""
    resolved, error = _validate_and_resolve(file_path, "Reading files")
    if error:
        return error
    
    try:
        with open(resolved, 'r', encoding='utf-8') as f:
            return _sanitize_output(f.read())
    except Exception as e:
        return _sanitize_output(f"Error reading file: {str(e)}")


def write_local_file(
    file_path: Annotated[str, Field(description="Relative path to the file within the workspace, e.g. 'dummy-repo/tests/test_app.py'")],
    content: Annotated[str, Field(description="Content to write")]
) -> str:
    """Write content to a file in the workspace. Use relative paths like 'dummy-repo/tests/test_app.py'."""
    resolved, error = _validate_and_resolve(file_path, "Writing files")
    if error:
        return error
    
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to: {file_path}"
    except Exception as e:
        return _sanitize_output(f"Error writing file: {str(e)}")


def list_local_files(
    directory: Annotated[str, Field(description="Relative directory path within the workspace, e.g. 'dummy-repo' or 'dummy-repo/tests'")],
    pattern: Annotated[str, Field(description="File pattern (e.g., '*.py')")] = "*"
) -> str:
    """List files in a directory within the workspace. Use relative paths like 'dummy-repo'."""
    resolved, error = _validate_and_resolve(directory, "Listing files")
    if error:
        return error
    
    try:
        workspace = _get_allowed_workspace()
        files = list(resolved.rglob(pattern))
        # Filter out common non-code directories
        files = [f for f in files if not any(
            skip in str(f) for skip in ['.git', '__pycache__', 'node_modules', '.venv', '.pytest_cache']
        )]
        # Return paths relative to workspace for cleaner output
        relative_files = []
        for f in files[:100]:
            try:
                relative_files.append(str(f.relative_to(workspace)))
            except ValueError:
                relative_files.append(str(f))
        return "\n".join(relative_files)
    except Exception as e:
        return _sanitize_output(f"Error listing files: {str(e)}")


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
    test_path: Annotated[str, Field(description="Relative path to test file or directory, e.g. 'dummy-repo/tests' or 'dummy-repo/tests/test_app.py'")],
    verbose: Annotated[bool, Field(description="Enable verbose output")] = True
) -> str:
    """Run pytest on specified path within the workspace. Use relative paths."""
    resolved, error = _validate_and_resolve(test_path, "Running pytest")
    if error:
        return error
    
    # Ensure pytest is installed
    install_error = _ensure_pytest_installed()
    if install_error:
        return install_error
    
    try:
        cmd = [sys.executable, "-m", "pytest", str(resolved)]
        if verbose:
            cmd.append("-v")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(resolved.parent) if resolved.is_file() else str(resolved)
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n\nSTDERR:\n{result.stderr}"
        
        status = "PASSED" if result.returncode == 0 else "FAILED"
        return _sanitize_output(f"Pytest {status} (exit code: {result.returncode})\n\n{output}")
    except subprocess.TimeoutExpired:
        return "Error: Pytest timed out after 120 seconds"
    except Exception as e:
        return _sanitize_output(f"Error running pytest: {str(e)}")


def run_pytest_with_coverage(
    test_path: Annotated[str, Field(description="Relative path to test file or directory, e.g. 'dummy-repo/tests'")],
    source_path: Annotated[str, Field(description="Relative path to source code to measure coverage for, e.g. 'dummy-repo/app.py'")]
) -> str:
    """Run pytest with coverage report. Use relative paths for both arguments."""
    resolved_test, error = _validate_and_resolve(test_path, "Running pytest")
    if error:
        return error
    resolved_source, error = _validate_and_resolve(source_path, "Measuring coverage")
    if error:
        return error
    
    # Ensure pytest is installed
    install_error = _ensure_pytest_installed()
    if install_error:
        return install_error
    
    try:
        cmd = [
            sys.executable, "-m", "pytest",
            str(resolved_test),
            f"--cov={resolved_source}",
            "--cov-report=term-missing",
            "-v"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(resolved_test.parent) if resolved_test.is_file() else str(resolved_test)
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n\nSTDERR:\n{result.stderr}"
        
        return _sanitize_output(f"Coverage Report:\n{output}")
    except subprocess.TimeoutExpired:
        return "Error: Pytest with coverage timed out after 180 seconds"
    except Exception as e:
        return _sanitize_output(f"Error running pytest with coverage: {str(e)}")

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
