"""
Unit Test Orchestration - Coordinates multi-agent workflow for pytest test generation
using the declarative WorkflowBuilder pattern.
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
from enum import Enum

import git
from agent_framework import (
    WorkflowBuilder,
    AgentExecutor,
    AgentExecutorResponse,
    FunctionExecutor,
    Case,
    Default,
    Workflow,
    WorkflowContext,
)

from agents import (
    create_verifier_agent,
    create_planner_agent,
    create_implementer_agent,
    create_reviewer_agent,
)
from services.azure_devops_service import create_devops_service_from_env

# Flags for test and approved tests

class VerifierDecision(str, Enum):
    """Verifier agent decisions"""
    TESTS_CORRECT = "tests_correct"      # Tests exist and are correct → PR
    TESTS_NEEDED = "tests_needed"        # Tests missing or incorrect → Planner


class ReviewerDecision(str, Enum):
    """Reviewer agent decisions"""
    APPROVED = "approved"                # Review passed → PR
    REVISE = "revise"                    # Review failed → back to Planner


@dataclass
class OrchestrationConfig:
    """Configuration for the orchestration workflow"""
    workspace_path: str
    target_branch: str = "main"
    feature_branch_prefix: str = "feature/add-tests-"
    pr_labels: list = field(default_factory=lambda: ["auto-generated", "unit-tests"])
    max_revision_iterations: int = 3


async def _route_verifier_decision(response: AgentExecutorResponse, ctx: WorkflowContext[VerifierDecision]) -> None:
    """Route based on verifier agent's decision.
    
    Args:
        response: AgentExecutorResponse from verifier agent
        ctx: Workflow context with shared state
    """
    # Extract text from agent response
    message = response.agent_response.text if response.agent_response else ""
    
    print(f"\n🔍 Verifier analysis complete.")
    
    # Get run kwargs from shared state
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    results = run_kwargs.get("results", {"steps": []})
    
    # Store the verifier output
    await ctx.set_shared_state("verifier_report", message)
    
    # Verifying if test exists and are correct
    if "VERDICT: TESTS_CORRECT" in message.upper() or "TESTS_CORRECT" in message.upper():
        print("   ✅ Tests are correct! Proceeding to create PR.")
        results["steps"].append({
            "step": "verify", 
            "success": True,
            "decision": "tests_correct"
        })
        await ctx.send_message(VerifierDecision.TESTS_CORRECT)
    else:
        print("   📝 Tests needed. Proceeding to planning...")
        results["steps"].append({
            "step": "verify", 
            "success": True,
            "decision": "tests_needed"
        })
        await ctx.send_message(VerifierDecision.TESTS_NEEDED)


async def _route_reviewer_decision(response: AgentExecutorResponse, ctx: WorkflowContext[ReviewerDecision]) -> None:
    """Route based on reviewer agent's decision.
    
    Args:
        response: AgentExecutorResponse from reviewer agent
        ctx: Workflow context with shared state
    """
    # Extract text from agent response
    message = response.agent_response.text if response.agent_response else ""
    
    # Get run kwargs from shared state
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    
    # Get revision_count (may not exist yet)
    try:
        revision_count = await ctx.get_shared_state("revision_count")
    except KeyError:
        revision_count = run_kwargs.get("revision_count", 0)
    
    max_revisions = run_kwargs.get("max_revisions", 3)
    results = run_kwargs.get("results", {"steps": []})
    
    print(f"\n🔎 Review complete (revision #{revision_count + 1}).")
    
    # Store review output
    await ctx.set_shared_state("review_summary", message)
    
    # Check for approval indicators
    approved_indicators = ["APPROVED", "LGTM", "LOOKS GOOD", "REVIEW: PASSED", "VERDICT: APPROVED"]
    revise_indicators = ["REVISE", "NEEDS WORK", "CHANGES NEEDED", "REVIEW: FAILED", "VERDICT: REVISE"]
    
    is_approved = any(ind in message.upper() for ind in approved_indicators)
    needs_revision = any(ind in message.upper() for ind in revise_indicators)
    
    # Force approval if max revisions reached, COMMENT: Should we have this?
    if revision_count >= max_revisions:
        print(f"   ⚠️ Max revisions ({max_revisions}) reached. Proceeding with PR.")
        is_approved = True
        needs_revision = False
    
    if is_approved and not needs_revision:
        print("   ✅ Review passed! Proceeding to create PR.")
        results["steps"].append({
            "step": "review", 
            "success": True,
            "decision": "approved",
            "revision": revision_count + 1
        })
        await ctx.send_message(ReviewerDecision.APPROVED)
    else:
        print("   🔄 Revision needed. Going back to planner...")
        await ctx.set_shared_state("revision_count", revision_count + 1)
        await ctx.set_shared_state("review_feedback", message)
        results["steps"].append({
            "step": "review", 
            "success": True,
            "decision": "revise",
            "revision": revision_count + 1
        })
        await ctx.send_message(ReviewerDecision.REVISE)

#-----------------------------Creating Pull Request-----------------------------#
async def _create_pull_request(message: Any, ctx: WorkflowContext[str]) -> None:
    """Create branch, commit, push, and create PR.
    
    Args:
        message: Output from previous executor (decision enum or string)
        ctx: Workflow context with shared state
    """
    print("\n🚀 Creating pull request...")
    
    # Get run kwargs from shared state
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    repo_path = run_kwargs.get("repo_path")
    config = run_kwargs.get("config")
    devops_service = run_kwargs.get("devops_service")
    results = run_kwargs.get("results", {"steps": []})
    
    branch_name = f"{config.feature_branch_prefix}{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    try:
        # Create branch on remote
        await devops_service.create_branch(branch_name, config.target_branch)
        
        # Commit and push local changes
        repo = git.Repo(repo_path)
        
        # Check if already on a branch or detached HEAD
        try:
            repo.git.checkout('-b', branch_name)
        except git.GitCommandError:
            repo.git.checkout(branch_name)
        
        repo.git.add('--all')
        
        if repo.is_dirty() or repo.untracked_files:
            repo.index.commit("Add/update pytest unit tests")
            origin = repo.remote('origin')
            origin.push(branch_name, set_upstream=True)
            
            # Build PR description
            verifier_report = str(await ctx.get_shared_state("verifier_report") or "")[:500]
            review_summary = str(await ctx.get_shared_state("review_summary") or "")[:500]
            
            description = f"""This PR adds/updates pytest unit tests.

**Verification Report:**
{verifier_report}...

**Review Summary:**
{review_summary}...

---
*Generated by Unit Test Orchestration Agent*
"""
            
            # Create PR
            pr = await devops_service.create_pull_request(
                source_branch=branch_name,
                target_branch=config.target_branch,
                title="Add pytest unit tests",
                description=description,
                labels=config.pr_labels
            )
            
            results["steps"].append({
                "step": "create_pr", 
                "success": True,
                "pr_id": pr["id"], 
                "url": pr.get("url")
            })
            print(f"   ✅ PR #{pr['id']} created!")
            await ctx.send_message(f"Pull request #{pr['id']} created successfully!")
        else:
            print("   ℹ️ No changes to commit.")
            results["steps"].append({
                "step": "create_pr", 
                "success": True,
                "status": "skipped", 
                "reason": "no changes"
            })
            await ctx.send_message("No changes to commit - skipping PR creation.")
            
    except Exception as e:
        print(f"   ❌ PR creation failed: {e}")
        results["steps"].append({
            "step": "create_pr", 
            "success": False,
            "error": str(e)
        })
        raise


async def _handle_complete(message: str, ctx: WorkflowContext[str, str]) -> None:
    """Handle workflow completion."""
    print("\n✅ Workflow completed successfully!")
    await ctx.yield_output("Workflow completed")


#-----------------------------UnitTestOrchestration Class-----------------------------#
class UnitTestOrchestration:
    """
    Orchestrates the multi-agent workflow for generating pytest unit tests
    using the declarative WorkflowBuilder pattern.
    
    Workflow:
                        ┌──────────────┐
                        │    Clone     │ (code)
                        └──────┬───────┘
                               ▼
                        ┌──────────────┐
                        │   Verifier   │
                        └──────┬───────┘
                               │
              ┌────────────────┴────────────────┐
              │ TESTS_CORRECT                   │ TESTS_NEEDED
              ▼                                 ▼
        ┌──────────┐                     ┌──────────────┐
        │Create PR │                     │   Planner    │◄──────┐
        └──────────┘                     └──────┬───────┘       │
                                                ▼               │
                                         ┌──────────────┐       │
                                         │ Implementer  │       │
                                         └──────┬───────┘       │
                                                ▼               │
                                         ┌──────────────┐       │
                                         │   Reviewer   │       │
                                         └──────┬───────┘       │
                                                │               │
                               ┌────────────────┴───────┐       │
                               │ APPROVED               │ REVISE│
                               ▼                        └───────┘
                         ┌──────────┐
                         │Create PR │
                         └──────────┘
    """
    
    def __init__(self, config: OrchestrationConfig):
        self.config = config
        self.devops_service = None
        self.workflow: Optional[Workflow] = None
        self._repo_path: Optional[str] = None
        
    async def initialize(self):
        """Initialize the DevOps service and build the workflow"""
        if self.workflow is not None:
            return
        
        # Create DevOps service for clone/PR operations
        self.devops_service = create_devops_service_from_env()
        
        # Build repo path (resolve to absolute)
        repo_name = os.getenv("AZURE_DEVOPS_REPO_NAME", "")
        self._repo_path = os.path.abspath(os.path.join(self.config.workspace_path, repo_name))
        
        # Create agents
        verifier_agent = create_verifier_agent()
        planner_agent = create_planner_agent()
        implementer_agent = create_implementer_agent()
        reviewer_agent = create_reviewer_agent()
        
        # Create agent executors
        verifier_executor = AgentExecutor(verifier_agent, id="verifier")
        planner_executor = AgentExecutor(planner_agent, id="planner")
        implementer_executor = AgentExecutor(implementer_agent, id="implementer")
        reviewer_executor = AgentExecutor(reviewer_agent, id="reviewer")
        
        # Create function executors for routing and PR creation
        verifier_routing = FunctionExecutor(_route_verifier_decision, id="verifier_routing")
        reviewer_routing = FunctionExecutor(_route_reviewer_decision, id="reviewer_routing")
        create_pr_executor = FunctionExecutor(_create_pull_request, id="create_pr")
        handle_complete = FunctionExecutor(_handle_complete, id="complete")
        
        #----------------------------- Build Workflow -----------------------------#
        self.workflow = (
            WorkflowBuilder()
            .set_start_executor(verifier_executor)
            .add_edge(verifier_executor, verifier_routing)
            .add_switch_case_edge_group(
                verifier_routing,
                [
                    Case(condition=lambda msg: msg == VerifierDecision.TESTS_CORRECT, target=create_pr_executor),
                    Default(target=planner_executor),
                ]
            )
            .add_edge(planner_executor, implementer_executor)
            .add_edge(implementer_executor, reviewer_executor)
            .add_edge(reviewer_executor, reviewer_routing)
            .add_switch_case_edge_group(
                reviewer_routing,
                [
                    Case(condition=lambda msg: msg == ReviewerDecision.REVISE, target=planner_executor),
                    Default(target=create_pr_executor),  # Handles APPROVED and any fallback
                ]
            )
            .add_edge(create_pr_executor, handle_complete)
            # Calculate max iterations: initial(6) + revisions(4 each) + final(2) + buffer
            .set_max_iterations((self.config.max_revision_iterations + 1) * 6 + 10)
            .build()
        )
        
        print("✅ Workflow initialized successfully")
    
    async def run_workflow(self) -> dict:
        """
        Run the unit test generation workflow.
        
        Returns:
            Workflow result dictionary
        """
        await self.initialize()
        
        results = {
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "status": "running"
        }
        
        try:
            # Step 1: Clone Repository (direct code, before workflow)
            print("\n📥 Cloning repository...")
            await self.devops_service.clone_repository(
                self.config.workspace_path, 
                self.config.target_branch
            )
            results["steps"].append({"step": "clone", "success": True})
            print(f"   Cloned to: {self._repo_path}")
            
            # Set WORKSPACE_PATH so agent plugins can enforce path restrictions
            os.environ["WORKSPACE_PATH"] = self._repo_path
            print(f"   🔒 Agents restricted to workspace: {self._repo_path}")
            
            # Step 2: Run the agent workflow
            print("\n🚀 Starting agent workflow...")
            
            #----------------------------- Initial Message for Verifier -----------------------------#
            # Create initial message for verifier
            initial_message = f"""Analyze the code in {self._repo_path} and check if proper pytest unit tests exist.

Look for:
- Key functions and classes in the source code
- Existing test files (test_*.py or *_test.py)
- Whether critical code paths have test coverage
- If tests exist, verify they are CORRECT (pass, have good coverage, follow best practices)

Report:
1. List of key functions/classes found
2. Existing test files found
3. Test quality assessment (if tests exist)

IMPORTANT - End your response with exactly one of these verdicts:
- "VERDICT: TESTS_CORRECT" - if tests exist AND are correct/sufficient
- "VERDICT: TESTS_NEEDED" - if tests are missing, incomplete, or incorrect"""
            
            # Run the workflow with initial state passed via kwargs
            # These will be stored in SharedState under "_workflow_run_kwargs"
            workflow_result = await self.workflow.run(
                initial_message,
                repo_path=self._repo_path,
                config=self.config,
                devops_service=self.devops_service,
                results=results,
                revision_count=0,
                max_revisions=self.config.max_revision_iterations
            )
            
            # Extract final results from workflow outputs
            for event in workflow_result.events:
                # Check for output events that might contain results
                if hasattr(event, 'output'):
                    print(f"   Output: {event.output}")

            results["status"] = "completed"
            results["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)
            print(f"\n❌ Workflow failed: {e}")
            import traceback
            traceback.print_exc()
            
        return results
