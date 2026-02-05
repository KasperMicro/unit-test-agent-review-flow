"""
Unit Test Orchestration - Coordinates multi-agent workflow for pytest test generation
using the declarative WorkflowBuilder pattern.
"""
import os
from dataclasses import dataclass, field
from typing import Any, Optional
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
from agents.quality_evaluation import VerifierOutput, ReviewerOutput
from services.azure_devops_service import create_devops_service_from_env


class VerifierDecision(str, Enum):
    """Verifier agent decisions for workflow routing"""
    TESTS_CORRECT = "tests_correct"      # Tests exist and are correct → Complete
    TESTS_NEEDED = "tests_needed"        # Tests missing or incorrect → Planner


class ReviewerDecision(str, Enum):
    """Reviewer agent decisions for workflow routing"""
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
    """Route based on verifier agent's structured output decision.
    
    The agent uses response_format=VerifierOutput, so response.agent_response.value
    contains the parsed Pydantic model directly.
    
    Args:
        response: AgentExecutorResponse from verifier agent
        ctx: Workflow context with shared state
    """
    print(f"\n" + "="*70)
    print(f"🔍 VERIFIER AGENT - Analysis Complete")
    print("="*70)
    
    # Show agent's raw text output (truncated)
    text = response.agent_response.text or ""
    if text:
        print(f"\n📤 Agent Output (truncated):")
        print(f"   {text[:500]}..." if len(text) > 500 else f"   {text}")
    
    # Get run kwargs from shared state
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    results = run_kwargs.get("results", {"steps": []})
    
    # Get structured output directly from agent response (guaranteed by response_format)
    verifier_output: VerifierOutput = response.agent_response.value
    
    if verifier_output is None:
        # Fallback if response parsing somehow failed
        print("\n❌ Could not parse verifier response. Defaulting to tests needed.")
        await ctx.set_shared_state("verifier_report", text[:500])
        await ctx.set_shared_state("verifier_feedback", text)
        results["steps"].append({
            "step": "verify", 
            "success": False,
            "decision": "tests_needed",
            "error": "structured_output_missing"
        })
        await ctx.send_message(VerifierDecision.TESTS_NEEDED)
        return
    
    # Show structured decision
    print(f"\n📊 Structured Decision:")
    print(f"   tests_exist_and_correct = {verifier_output.tests_exist_and_correct}")
    print(f"\n💬 Feedback:")
    print(f"   {verifier_output.feedback}")
    
    # Store feedback for downstream agents
    await ctx.set_shared_state("verifier_report", verifier_output.feedback)
    await ctx.set_shared_state("verifier_feedback", verifier_output.feedback)
    
    if verifier_output.tests_exist_and_correct:
        print(f"\n➡️  Routing: TESTS_CORRECT → Workflow Complete (no changes needed)")
        results["steps"].append({
            "step": "verify", 
            "success": True,
            "decision": "tests_correct",
            "feedback": verifier_output.feedback
        })
        await ctx.send_message(VerifierDecision.TESTS_CORRECT)
    else:
        print(f"\n➡️  Routing: TESTS_NEEDED → Planner Agent")
        results["steps"].append({
            "step": "verify", 
            "success": True,
            "decision": "tests_needed",
            "feedback": verifier_output.feedback
        })
        await ctx.send_message(VerifierDecision.TESTS_NEEDED)


async def _route_reviewer_decision(response: AgentExecutorResponse, ctx: WorkflowContext[ReviewerDecision]) -> None:
    """Route based on reviewer agent's structured output decision.
    
    The agent uses response_format=ReviewerOutput, so response.agent_response.value
    contains the parsed Pydantic model directly.
    
    Args:
        response: AgentExecutorResponse from reviewer agent
        ctx: Workflow context with shared state
    """
    # Get run kwargs from shared state
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    
    # Get revision_count (may not exist yet)
    try:
        revision_count = await ctx.get_shared_state("revision_count")
    except KeyError:
        revision_count = run_kwargs.get("revision_count", 0)
    
    max_revisions = run_kwargs.get("max_revisions", 3)
    results = run_kwargs.get("results", {"steps": []})
    
    print(f"\n" + "="*70)
    print(f"🔎 REVIEWER AGENT - Review Complete (Revision #{revision_count + 1})")
    print("="*70)
    
    # Show agent's raw text output (truncated)
    text = response.agent_response.text or ""
    if text:
        print(f"\n📤 Agent Output (truncated):")
        print(f"   {text[:500]}..." if len(text) > 500 else f"   {text}")
    
    # Get structured output directly from agent response (guaranteed by response_format)
    reviewer_output: ReviewerOutput = response.agent_response.value
    
    if reviewer_output is None:
        # Fallback if response parsing somehow failed
        print("\n❌ Could not parse reviewer response!")
        text = response.agent_response.text or ""
        
        if revision_count >= max_revisions:
            print(f"   ⚠️ Max revisions reached. Forcing PR.")
            await ctx.set_shared_state("review_summary", f"Forced after {max_revisions} revisions")
            results["steps"].append({
                "step": "review", 
                "success": False,
                "decision": "approved",
                "revision": revision_count + 1,
                "error": "structured_output_missing"
            })
            await ctx.send_message(ReviewerDecision.APPROVED)
        else:
            print("   🔄 Forcing revision.")
            await ctx.set_shared_state("revision_count", revision_count + 1)
            await ctx.set_shared_state("review_feedback", text[:500])
            results["steps"].append({
                "step": "review", 
                "success": False,
                "decision": "revise",
                "revision": revision_count + 1,
                "error": "structured_output_missing"
            })
            await ctx.send_message(ReviewerDecision.REVISE)
        return
    
    print(f"\n📊 Structured Decision:")
    print(f"   approved = {reviewer_output.approved}")
    print(f"\n💬 Feedback:")
    print(f"   {reviewer_output.feedback}")
    
    # Store feedback for downstream agents
    await ctx.set_shared_state("review_summary", reviewer_output.feedback)
    
    # Check approval
    is_approved = reviewer_output.approved
    
    # Force approval if max revisions reached (escape hatch)
    if revision_count >= max_revisions and not is_approved:
        print(f"\n⚠️ Max revisions ({max_revisions}) reached. Forcing approval.")
        is_approved = True
    
    if is_approved:
        print(f"\n➡️  Routing: APPROVED → Create PR")
        results["steps"].append({
            "step": "review", 
            "success": True,
            "decision": "approved",
            "revision": revision_count + 1,
            "feedback": reviewer_output.feedback
        })
        await ctx.send_message(ReviewerDecision.APPROVED)
    else:
        print(f"\n➡️  Routing: REVISE → Planner Agent (revision #{revision_count + 2})")
        print(f"      Feedback: {reviewer_output.feedback[:150]}...")
        await ctx.set_shared_state("revision_count", revision_count + 1)
        await ctx.set_shared_state("review_feedback", reviewer_output.feedback)
        results["steps"].append({
            "step": "review", 
            "success": True,
            "decision": "revise",
            "revision": revision_count + 1,
            "feedback": reviewer_output.feedback
        })
        await ctx.send_message(ReviewerDecision.REVISE)


#-----------------------------Creating Pull Request-----------------------------#
async def _create_pull_request(message: Any, ctx: WorkflowContext[str]) -> None:
    """Create branch, commit, push, and create PR.
    
    Args:
        message: Output from previous executor (decision enum or string)
        ctx: Workflow context with shared state
    """
    print("\n" + "="*70)
    print("CODE CHANGES SUMMARY")
    print("="*70)
    
    # Get run kwargs from shared state
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    repo_path = run_kwargs.get("repo_path")
    config = run_kwargs.get("config")
    devops_service = run_kwargs.get("devops_service")
    results = run_kwargs.get("results", {"steps": []})
    
    # Check for changes BEFORE creating branch
    repo = git.Repo(repo_path)
    repo.git.add('--all')
    
    # Show detailed file changes
    if repo.untracked_files:
        print("\nNew Files Added:")
        for f in repo.untracked_files:
            print(f"   + {f}")
    
    # Show modified files  
    try:
        changed_files = [item.a_path for item in repo.index.diff(repo.head.commit)]
        if changed_files:
            print("\nModified Files:")
            for f in changed_files:
                print(f"   ~ {f}")
    except Exception:
        pass  # No previous commit to diff against
    
    if not repo.is_dirty() and not repo.untracked_files:
        print("\nNo changes to commit - skipping PR creation.")
        results["steps"].append({
            "step": "create_pr", 
            "success": True,
            "status": "skipped", 
            "reason": "no changes"
        })
        await ctx.send_message("No changes to commit - skipping PR creation.")
        return
    
    print("   🚀 Creating pull request...")
    branch_name = f"{config.feature_branch_prefix}{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    try:
        # Create branch on remote
        await devops_service.create_branch(branch_name, config.target_branch)
        
        # Checkout the new branch
        try:
            repo.git.checkout('-b', branch_name)
        except git.GitCommandError:
            repo.git.checkout(branch_name)
        
        # Stage changes again after checkout (in case checkout reset staging)
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
            # This shouldn't happen since we check early, but handle gracefully
            print("   ⚠️ Changes lost after checkout - no changes to commit.")
            results["steps"].append({
                "step": "create_pr", 
                "success": True,
                "status": "skipped", 
                "reason": "changes lost after checkout"
            })
            await ctx.send_message("No changes to commit after checkout.")
            
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


async def _handle_tests_already_correct(message: Any, ctx: WorkflowContext[str]) -> None:
    """Handle case when tests already exist and are correct - no PR needed."""
    print("\n✅ Tests already exist and are correct!")
    print("   ℹ️ No changes needed - skipping PR creation.")
    
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    results = run_kwargs.get("results", {"steps": []})
    results["steps"].append({
        "step": "complete", 
        "success": True,
        "status": "skipped",
        "reason": "tests_already_correct"
    })
    
    await ctx.yield_output("Tests already correct - no action needed")


async def _log_planner_output(response: AgentExecutorResponse, ctx: WorkflowContext[str]) -> None:
    """Log planner output before it goes to implementer."""
    print("\n" + "="*70)
    print("PLANNER AGENT - Output")
    print("="*70)
    
    output_text = str(response.agent_response.text) if response.agent_response else "No output"
    print("\nPlanner's Test Plan:")
    print("-"*50)
    # Show truncated output
    print(output_text[:1200] + "..." if len(output_text) > 1200 else output_text)
    print("-"*50)
    
    print("\n" + "="*70)
    print("IMPLEMENTER AGENT - Input") 
    print("="*70)
    print("  Receiving planner's test plan to implement...")
    
    # Forward the message
    await ctx.send_message(output_text)


async def _log_implementer_output(response: AgentExecutorResponse, ctx: WorkflowContext[str]) -> None:
    """Log implementer output before it goes to reviewer."""
    print("\n" + "="*70)
    print("IMPLEMENTER AGENT - Output")
    print("="*70)
    
    output_text = str(response.agent_response.text) if response.agent_response else "No output"
    print("\nImplementer's Response:")
    print("-"*50)
    # Show truncated output
    print(output_text[:1000] + "..." if len(output_text) > 1000 else output_text)
    print("-"*50)
    
    print("\n" + "="*70)
    print("REVIEWER AGENT - Input")
    print("="*70)
    print("  Reviewing implemented tests for quality...")
    
    # Forward the message
    await ctx.send_message(output_text)


async def _prepare_planner_from_verifier(message: Any, ctx: WorkflowContext[str]) -> None:
    """Prepare planner input with verifier feedback for initial planning."""
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    repo_path = run_kwargs.get("repo_path")
    
    # Get the verifier feedback (structured)
    try:
        verifier_feedback = await ctx.get_shared_state("verifier_feedback")
    except KeyError:
        verifier_feedback = "Tests are needed for this repository."
    
    # Get functions needing tests if available
    try:
        functions_needing_tests = await ctx.get_shared_state("functions_needing_tests")
        functions_list = "\n".join(f"  - {func}" for func in functions_needing_tests) if functions_needing_tests else ""
    except KeyError:
        functions_list = ""
    
    print(f"\n" + "="*70)
    print(f"📋 PLANNER AGENT - Input (Initial)")
    print("="*70)
    
    # Build a message for the planner with verifier's analysis
    planner_message = f"""CREATE TEST PLAN

The verifier has analyzed the repository and determined tests are needed.

**Repository Path:** {repo_path}

**Verifier Analysis:**
{verifier_feedback}
"""
    
    if functions_list:
        planner_message += f"""
**Functions/Classes Needing Tests:**
{functions_list}
"""
    
    planner_message += """
**Your Task:**
Create a comprehensive pytest test plan addressing the verifier's feedback.
Focus on the specific functions and gaps identified.
Ensure test coverage for edge cases and error handling."""
    
    print(f"\nInput Message to Planner:")
    print("-"*50)
    print(planner_message[:800] + "..." if len(planner_message) > 800 else planner_message)
    print("-"*50)
    await ctx.send_message(planner_message)


async def _prepare_planner_with_feedback(message: Any, ctx: WorkflowContext[str]) -> None:
    """Prepare planner input with structured review feedback when revision is needed."""
    run_kwargs = await ctx.get_shared_state("_workflow_run_kwargs") or {}
    repo_path = run_kwargs.get("repo_path")
    
    # Get the review feedback (structured)
    try:
        review_feedback = await ctx.get_shared_state("review_feedback")
    except KeyError:
        review_feedback = "No specific feedback provided."
    
    # Get specific issues if available
    try:
        review_issues = await ctx.get_shared_state("review_issues")
        issues_list = "\n".join(f"  - {issue}" for issue in review_issues) if review_issues else ""
    except KeyError:
        issues_list = ""
    
    try:
        revision_count = await ctx.get_shared_state("revision_count")
    except KeyError:
        revision_count = 1
    
    print(f"\n" + "="*70)
    print(f"📋 PLANNER AGENT - Input (Revision #{revision_count})")
    print("="*70)
    
    # Build a message for the planner that includes the structured feedback
    planner_message = f"""REVISION #{revision_count} REQUIRED

The previous test implementation was reviewed and needs improvements.

**Reviewer Feedback:**
{review_feedback}
"""
    
    if issues_list:
        planner_message += f"""
**Specific Issues to Address:**
{issues_list}
"""
    
    planner_message += f"""
**Your Task:**
Analyze the reviewer's feedback above and create an updated test plan for {repo_path}.
Address ALL issues mentioned in the feedback.
Focus on the specific problems identified by the reviewer.

Create a revised test plan that fixes these issues."""
    
    print(f"\n📥 Input Message to Planner:")
    print("-"*50)
    print(planner_message[:800] + "..." if len(planner_message) > 800 else planner_message)
    print("-"*50)
    await ctx.send_message(planner_message)


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
        │ Complete │                     │   Planner    │◄──────┐
        │no action │                     └──────┬───────┘       │
        └──────────┘                            ▼               │
                                         ┌──────────────┐       │
                                         │ Implementer  │       │
                                         └──────┬───────┘       │
                                                ▼               │
                                         ┌──────────────┐       │
                                         │   Reviewer   │       │
                                         └──────┬───────┘       │
                                                │               │
                               ┌────────────────┴───────┐       │
                               │ APPROVED               │ REVISE│ (with feedback)
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
        handle_tests_correct = FunctionExecutor(_handle_tests_already_correct, id="tests_correct")
        prepare_planner_initial = FunctionExecutor(_prepare_planner_from_verifier, id="prepare_initial")
        prepare_planner_revision = FunctionExecutor(_prepare_planner_with_feedback, id="prepare_revision")
        log_planner_output = FunctionExecutor(_log_planner_output, id="log_planner")
        log_implementer_output = FunctionExecutor(_log_implementer_output, id="log_implementer")
        
        #----------------------------- Build Workflow -----------------------------#
        self.workflow = (
            WorkflowBuilder()
            .set_start_executor(verifier_executor)
            .add_edge(verifier_executor, verifier_routing)
            .add_switch_case_edge_group(
                verifier_routing,
                [
                    # Tests already correct → complete without PR
                    Case(condition=lambda msg: msg == VerifierDecision.TESTS_CORRECT, target=handle_tests_correct),
                    # Tests needed → prepare planner with verifier feedback
                    Default(target=prepare_planner_initial),
                ]
            )
            # Route initial preparation to planner, log output, then to implementer
            .add_edge(prepare_planner_initial, planner_executor)
            .add_edge(planner_executor, log_planner_output)
            .add_edge(log_planner_output, implementer_executor)
            .add_edge(implementer_executor, log_implementer_output)
            .add_edge(log_implementer_output, reviewer_executor)
            .add_edge(reviewer_executor, reviewer_routing)
            .add_switch_case_edge_group(
                reviewer_routing,
                [
                    # Revision needed → prepare feedback and go to planner
                    Case(condition=lambda msg: msg == ReviewerDecision.REVISE, target=prepare_planner_revision),
                    # Approved → create PR
                    Default(target=create_pr_executor),
                ]
            )
            # Route revision preparation to planner
            .add_edge(prepare_planner_revision, planner_executor)
            .add_edge(create_pr_executor, handle_complete)
            # Calculate max iterations: initial(7) + revisions(5 each with feedback step) + final(2) + buffer
            .set_max_iterations((self.config.max_revision_iterations + 1) * 7 + 12)
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
            print("\n" + "="*70)
            print("STARTING AGENT WORKFLOW")
            print("="*70)
            
            #----------------------------- Initial Message for Verifier -----------------------------#
            print("\n" + "="*70)
            print("VERIFIER AGENT - Input")
            print("="*70)
            
            # Create initial message for verifier (uses structured output)
            initial_message = f"""Analyze the code in {self._repo_path} and check if proper pytest unit tests exist.

Look for:
- Key functions and classes in the source code
- Existing test files (test_*.py or *_test.py)
- Whether critical code paths have test coverage
- If tests exist, run them to verify they pass and follow best practices

Analyze and report on:
1. List of key functions/classes found
2. Existing test files found
3. Test quality assessment (if tests exist)
4. Gaps in test coverage

Your structured output will determine the next steps in the workflow."""
            
            print("\nInput Message:")
            print("-"*50)
            print(initial_message[:600] + "..." if len(initial_message) > 600 else initial_message)
            print("-"*50)
            
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
            outputs = workflow_result.get_outputs()
            for output in outputs:
                print(f"   Output: {output}")

            results["status"] = "completed"
            results["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)
            print(f"\n❌ Workflow failed: {e}")
            import traceback
            traceback.print_exc()
            
        return results
