"""
Main entry point for the Agent Orchestration application.

This application orchestrates AI agents to analyze code repositories
and generate comprehensive pytest unit tests.
"""
import asyncio
import argparse
import os
from dotenv import load_dotenv

from orchestration import UnitTestOrchestration, OrchestrationConfig


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Run agent orchestration for generating pytest unit tests"
    )
    
    parser.add_argument(
        "--branch",
        default=None,
        help="Target branch to clone from and create PR against (default: from env or 'main')"
    )
    
    parser.add_argument(
        "--workspace",
        default=None,
        help="Local workspace path for cloned code"
    )
    
    parser.add_argument(
        "--labels",
        nargs="+",
        default=None,
        help="Labels/tags to add to the PR (e.g., 'auto-generated' 'unit-tests')"
    )
    
    return parser.parse_args()


async def run_orchestration(args):
    """Run the orchestration workflow"""
    load_dotenv()
    
    # Get branch from args or environment
    target_branch = args.branch or os.getenv("AZURE_DEVOPS_DEFAULT_BRANCH", "main")
    
    # Get labels from args or environment
    pr_labels = args.labels
    if not pr_labels:
        env_labels = os.getenv("PR_LABELS")
        if env_labels:
            pr_labels = [l.strip() for l in env_labels.split(",")]
    
    # Build configuration
    config = OrchestrationConfig(
        workspace_path=args.workspace or os.getenv("WORKSPACE_PATH", "./workspace"),
        target_branch=target_branch,
        feature_branch_prefix="feature/add-unit-tests-",
        pr_labels=pr_labels
    )
    
    # Create orchestration
    orchestration = UnitTestOrchestration(config)
    
    print("=" * 70)
    print("🧪 Agent Orchestration - Unit Test Generation Pipeline")
    print("=" * 70)
    print(f"Target branch: {target_branch}")
    print(f"Workspace: {config.workspace_path}")
    if pr_labels:
        print(f"PR Labels: {pr_labels}")
    print("=" * 70)
    
    # Run the workflow
    results = await orchestration.run_workflow()
    
    # Print results summary
    print("\n📋 Workflow Results:")
    print(f"  Status: {results.get('status', 'unknown')}")
    
    if results.get("pr_url"):
        print(f"  PR URL: {results['pr_url']}")
    
    if results.get("steps"):
        print("\n  Steps completed:")
        for step in results["steps"]:
            status_icon = "✅" if step.get("success") else "❌"
            print(f"    {status_icon} {step['step']}")
    
    print("\n✅ Orchestration complete!")


def main():
    """Main function"""
    args = parse_args()
    asyncio.run(run_orchestration(args))


if __name__ == "__main__":
    main()
