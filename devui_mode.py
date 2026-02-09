"""
DevUI Mode - Interactive testing interface for agents and workflows.

This serves the unit test generation agents via a web UI for interactive testing.
Run with: python devui_mode.py
"""

import logging
import os
from typing import Any
from dotenv import load_dotenv

from agent_framework import AgentExecutor, AgentExecutorResponse, WorkflowBuilder, WorkflowContext, FunctionExecutor, Case, Default
from agent_framework.devui import serve

from agents.agent_definitions import (
    create_verifier_agent,
    create_planner_agent,
    create_implementer_agent,
    create_reviewer_agent,
)
from agents.models import VerifierOutput, ReviewerOutput
from orchestration import VerifierDecision, ReviewerDecision


#----------------------------- Simplified Routing for DevUI -----------------------------#
async def _devui_route_verifier(response: AgentExecutorResponse, ctx: WorkflowContext[VerifierDecision]) -> None:
    """Route based on verifier decision for DevUI demo."""
    verifier_output: VerifierOutput = response.agent_response.value
    
    if verifier_output is None:
        print("❌ Could not parse verifier response")
        await ctx.send_message(VerifierDecision.TESTS_NEEDED)
        return
    
    print(f"\n📊 Verifier Decision: tests_exist_and_correct = {verifier_output.tests_exist_and_correct}")
    print(f"💬 Feedback: {verifier_output.feedback[:200]}...")
    
    if verifier_output.tests_exist_and_correct:
        await ctx.send_message(VerifierDecision.TESTS_CORRECT)
    else:
        await ctx.send_message(VerifierDecision.TESTS_NEEDED)


async def _devui_route_reviewer(response: AgentExecutorResponse, ctx: WorkflowContext[ReviewerDecision]) -> None:
    """Route based on reviewer decision for DevUI demo."""
    reviewer_output: ReviewerOutput = response.agent_response.value
    
    if reviewer_output is None:
        print("❌ Could not parse reviewer response")
        await ctx.send_message(ReviewerDecision.REVISE)
        return
    
    print(f"\n📊 Reviewer Decision: approved = {reviewer_output.approved}")
    print(f"💬 Feedback: {reviewer_output.feedback[:200]}...")
    
    if reviewer_output.approved:
        await ctx.send_message(ReviewerDecision.APPROVED)
    else:
        await ctx.send_message(ReviewerDecision.REVISE)


async def _devui_forward_to_planner(message: Any, ctx: WorkflowContext[str]) -> None:
    """Forward verifier feedback to planner."""
    print(f"\n➡️ Forwarding to Planner...")
    await ctx.send_message(f"Create a test plan based on this analysis:\n{message}")


async def _devui_forward_to_implementer(response: AgentExecutorResponse, ctx: WorkflowContext[str]) -> None:
    """Forward planner output to implementer."""
    text = response.agent_response.text or "No plan provided"
    print(f"\n➡️ Forwarding to Implementer...")
    await ctx.send_message(text)


async def _devui_forward_to_reviewer(response: AgentExecutorResponse, ctx: WorkflowContext[str]) -> None:
    """Forward implementer output to reviewer."""
    text = response.agent_response.text or "No implementation provided"
    print(f"\n➡️ Forwarding to Reviewer...")
    await ctx.send_message(text)


async def _devui_complete(message: Any, ctx: WorkflowContext[str, str]) -> None:
    """Handle workflow completion."""
    print(f"\n✅ Workflow Complete!")
    await ctx.yield_output(f"Workflow completed with result: {message}")


async def _devui_tests_correct(message: Any, ctx: WorkflowContext[str, str]) -> None:
    """Handle tests already correct case."""
    print(f"\n✅ Tests already exist and are correct!")
    await ctx.yield_output("Tests already correct - no changes needed")


def create_devui_workflow():
    """Create a simplified workflow for DevUI testing."""
    # Create agents
    verifier = create_verifier_agent()
    planner = create_planner_agent()
    implementer = create_implementer_agent()
    reviewer = create_reviewer_agent()
    
    # Create executors
    verifier_exec = AgentExecutor(verifier, id="verifier")
    planner_exec = AgentExecutor(planner, id="planner")
    implementer_exec = AgentExecutor(implementer, id="implementer")
    reviewer_exec = AgentExecutor(reviewer, id="reviewer")
    
    # Create function executors
    verifier_routing = FunctionExecutor(_devui_route_verifier, id="verifier_routing")
    reviewer_routing = FunctionExecutor(_devui_route_reviewer, id="reviewer_routing")
    forward_to_planner = FunctionExecutor(_devui_forward_to_planner, id="forward_planner")
    forward_to_implementer = FunctionExecutor(_devui_forward_to_implementer, id="forward_implementer")
    forward_to_reviewer = FunctionExecutor(_devui_forward_to_reviewer, id="forward_reviewer")
    complete = FunctionExecutor(_devui_complete, id="complete")
    tests_correct = FunctionExecutor(_devui_tests_correct, id="tests_correct")
    
    # Build workflow
    workflow = (
        WorkflowBuilder(
            name="Unit Test Generation",
            description="Analyzes code, plans tests, implements them, and reviews quality"
        )
        .set_start_executor(verifier_exec)
        .add_edge(verifier_exec, verifier_routing)
        .add_switch_case_edge_group(
            verifier_routing,
            [
                Case(condition=lambda msg: msg == VerifierDecision.TESTS_CORRECT, target=tests_correct),
                Default(target=forward_to_planner),
            ]
        )
        .add_edge(forward_to_planner, planner_exec)
        .add_edge(planner_exec, forward_to_implementer)
        .add_edge(forward_to_implementer, implementer_exec)
        .add_edge(implementer_exec, forward_to_reviewer)
        .add_edge(forward_to_reviewer, reviewer_exec)
        .add_edge(reviewer_exec, reviewer_routing)
        .add_switch_case_edge_group(
            reviewer_routing,
            [
                Case(condition=lambda msg: msg == ReviewerDecision.REVISE, target=forward_to_planner),
                Default(target=complete),
            ]
        )
        .set_max_iterations(20)
        .build()
    )
    
    return workflow


def main():
    """Launch DevUI with all unit test generation agents and workflow."""
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)
    
    # Set workspace path for agent file restrictions
    workspace_path = os.path.abspath(os.getenv("WORKSPACE_PATH", "./cloned_code"))
    os.environ["WORKSPACE_PATH"] = workspace_path
    
    logger.info("="*60)
    logger.info("🧪 Agent Orchestration - DevUI Mode")
    logger.info("="*60)
    logger.info(f"Workspace path: {workspace_path}")
    logger.info("")
    
    # Create agents
    logger.info("Creating agents...")
    verifier = create_verifier_agent()
    planner = create_planner_agent()
    implementer = create_implementer_agent()
    reviewer = create_reviewer_agent()
    
    # Create workflow
    logger.info("Creating workflow...")
    workflow = create_devui_workflow()
    
    # Collect entities for serving
    entities = [verifier, planner, implementer, reviewer, workflow]
    
    logger.info("")
    logger.info("Available entities:")
    logger.info("  Agents:")
    logger.info("    - VerifierAgent: Analyzes code and checks for existing tests")
    logger.info("    - PlannerAgent: Creates detailed test plans")
    logger.info("    - ImplementerAgent: Writes pytest tests")
    logger.info("    - ReviewerAgent: Reviews test quality")
    logger.info("  Workflow:")
    logger.info("    - Unit Test Generation: Full pipeline (Verifier → Planner → Implementer → Reviewer)")
    logger.info("")
    logger.info("Starting DevUI on http://localhost:8090")
    logger.info("="*60)
    
    # Launch server (opens browser automatically)
    serve(entities=entities, port=8090, auto_open=True)


if __name__ == "__main__":
    main()
