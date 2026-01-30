"""
Main entry point for the Agent Orchestration application
"""
import asyncio
import argparse
import os
from dotenv import load_dotenv

from orchestration import LoggingEnhancementOrchestration, OrchestrationConfig


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Run agent orchestration for adding logging to code"
    )
    
    parser.add_argument(
        "--mode",
        choices=["sequential", "collaborative"],
        default="sequential",
        help="Orchestration mode: sequential (step-by-step) or collaborative (agent chat)"
    )
    
    parser.add_argument(
        "--branch",
        default=None,
        help="Target branch to clone from and create PR against (default: from env or 'main')"
    )
    
    parser.add_argument(
        "--patterns",
        nargs="+",
        default=["*.py"],
        help="File patterns to process (e.g., '*.py' '*.cs')"
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
        help="Labels/tags to add to the PR (e.g., 'auto-generated' 'logging')"
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
        feature_branch_prefix="feature/add-logging-",
        pr_labels=pr_labels
    )
    
    # Create orchestration
    orchestration = LoggingEnhancementOrchestration(config)
    
    print("=" * 70)
    print("🤖 Agent Orchestration - Logging Enhancement Pipeline")
    print("=" * 70)
    print(f"Mode: {args.mode}")
    print(f"Target branch: {target_branch}")
    print(f"File patterns: {args.patterns}")
    print(f"Workspace: {config.workspace_path}")
    if pr_labels:
        print(f"PR Labels: {pr_labels}")
    print("=" * 70)
    
    if args.mode == "sequential":
        # Run step-by-step workflow
        results = await orchestration.run_sequential_workflow(
            file_patterns=args.patterns
        )
        
        # Print detailed results
        print("\n📋 Detailed Results:")
        for step in results.get("steps", []):
            print(f"\n  📌 {step['step'].upper()}")
            result_preview = step.get('result', 'N/A')[:200]
            print(f"     {result_preview}...")
            
    else:
        # Run collaborative multi-agent chat
        initial_message = f"""Please enhance the code with logging. The workflow is:
1. Clone the repository from Azure DevOps to {config.workspace_path}
2. Analyze the code to find where logging is needed (focus on {args.patterns})
3. Add logging according to our logging standards
4. Create a feature branch, push changes, and create a pull request

Start by cloning the repository."""
        
        messages = await orchestration.run_collaborative_workflow(initial_message)
        
        print(f"\n📋 Conversation had {len(messages)} messages")
    
    print("\n✅ Orchestration complete!")


def main():
    """Main function"""
    args = parse_args()
    asyncio.run(run_orchestration(args))


if __name__ == "__main__":
    main()
