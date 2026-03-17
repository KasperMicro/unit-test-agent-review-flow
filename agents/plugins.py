"""
Agent Tools — Custom tools for Copilot SDK agents.

The Copilot SDK provides built-in tools for file I/O and shell execution,
so only project-specific tools are defined here.
"""
from pathlib import Path


def get_testing_standards() -> str:
    """Get the testing standards documentation for pytest best practices."""
    try:
        root = Path(__file__).parent.parent
        standards_file = root / "config" / "testing_standards.md"

        with open(standards_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading testing standards: {str(e)}"
