"""
Agent Orchestration - Coordinates multi-agent workflow for code logging enhancement
"""
import asyncio
import os
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from agent_framework import ChatAgent

from agents import (
    create_devops_agent,
    create_code_analyzer_agent,
    create_logging_agent,
    create_orchestrator_agent
)


@dataclass
class OrchestrationConfig:
    """Configuration for the orchestration workflow"""
    workspace_path: str
    target_branch: str = "main"
    feature_branch_prefix: str = "feature/add-logging-"
    max_iterations: int = 20
    pr_labels: list = None  # Labels to add to created PRs


class LoggingEnhancementOrchestration:
    """
    Orchestrates the multi-agent workflow for enhancing code with logging.
    
    Workflow:
    1. Clone repository from Azure DevOps
    2. Analyze code to identify logging needs
    3. Add logging according to standards
    4. Create PR with changes
    """
    
    def __init__(self, config: OrchestrationConfig):
        self.config = config
        self._agents_initialized = False
        self.devops_agent: Optional[ChatAgent] = None
        self.analyzer_agent: Optional[ChatAgent] = None
        self.logging_agent: Optional[ChatAgent] = None
        self.orchestrator_agent: Optional[ChatAgent] = None
        
    async def initialize(self):
        """Initialize the agents"""
        if self._agents_initialized:
            return
        
        # Create all agents
        self.devops_agent = create_devops_agent()
        self.analyzer_agent = create_code_analyzer_agent()
        self.logging_agent = create_logging_agent()
        self.orchestrator_agent = create_orchestrator_agent()
        
        self._agents_initialized = True
        print("✅ Agents initialized successfully")
    
    async def run_sequential_workflow(self, file_patterns: list[str] = None) -> dict:
        """
        Run the orchestration workflow sequentially.
        This provides more control over the workflow steps.
        
        Args:
            file_patterns: Optional list of file patterns to process (e.g., ["*.py", "*.cs"])
            
        Returns:
            Workflow result dictionary
        """
        await self.initialize()
        
        results = {
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "status": "running"
        }
        
        # Build the full repo path (workspace + repo name from env)
        repo_name = os.getenv("AZURE_DEVOPS_REPO_NAME", "")
        repo_path = os.path.join(self.config.workspace_path, repo_name)
        
        try:
            # Step 1: Clone Repository
            print("\n📥 Step 1: Cloning repository...")
            clone_response = await self._invoke_agent(
                self.devops_agent,
                f"Clone the repository to {self.config.workspace_path} from branch {self.config.target_branch}"
            )
            results["steps"].append({"step": "clone", "result": clone_response})
            print(f"   Result: {clone_response[:200]}...")
            
            # Step 2: Create Feature Branch
            branch_name = f"{self.config.feature_branch_prefix}{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            print(f"\n🌿 Step 2: Creating feature branch '{branch_name}'...")
            branch_response = await self._invoke_agent(
                self.devops_agent,
                f"Create a new branch named '{branch_name}' from '{self.config.target_branch}'"
            )
            results["steps"].append({"step": "create_branch", "branch": branch_name, "result": branch_response})
            print(f"   Result: {branch_response[:200]}...")
            
            # Step 3: Analyze Code
            print("\n🔍 Step 3: Analyzing code for logging opportunities...")
            analyze_prompt = f"""Analyze the code in {repo_path} to identify where logging should be added.
Look for:
- Functions that need entry/exit logging
- Error handling that should log exceptions
- External API calls that need logging
- Database operations that need logging
Focus on files matching: {file_patterns or ['*.py', '*.cs', '*.js']}"""
            
            analysis_response = await self._invoke_agent(self.analyzer_agent, analyze_prompt)
            results["steps"].append({"step": "analyze", "result": analysis_response})
            print(f"   Analysis complete. Found recommendations.")
            
            # Step 4: Add Logging
            print("\n📝 Step 4: Adding logging to code...")
            logging_prompt = f"""Based on this analysis:
{analysis_response}

Add appropriate logging to the code files in {repo_path}.
Follow the logging standards documentation.
Write the modified files back to the workspace."""
            
            logging_response = await self._invoke_agent(self.logging_agent, logging_prompt)
            results["steps"].append({"step": "add_logging", "result": logging_response})
            print(f"   Logging added to files.")
            
            # Step 5: Push Changes and Create PR
            print("\n🚀 Step 5: Pushing changes and creating pull request...")
            labels_instruction = ""
            if self.config.pr_labels:
                labels_instruction = f"\n- Labels: {self.config.pr_labels}"
            
            pr_prompt = f"""Use the commit_and_push_local_changes tool to commit and push all modified files:
- repo_path: '{repo_path}'
- branch_name: '{branch_name}'
- commit_message: 'Add logging statements for improved observability'

After pushing successfully, create a pull request:
- source_branch: '{branch_name}'
- target_branch: '{self.config.target_branch}'
- title: 'Add logging to improve observability'
- description: 'This PR adds logging statements according to our logging standards.\\n\\nChanges made:\\n{logging_response[:800]}'{labels_instruction}"""
            
            pr_response = await self._invoke_agent(self.devops_agent, pr_prompt)
            results["steps"].append({"step": "create_pr", "result": pr_response})
            print(f"   PR created successfully!")
            
            results["status"] = "completed"
            results["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            results["status"] = "failed"
            results["error"] = str(e)
            print(f"\n❌ Workflow failed: {e}")
            
        return results
    
    async def run_collaborative_workflow(self, initial_message: str) -> list:
        """
        Run a collaborative multi-agent chat workflow.
        Agents work together in a sequential handoff pattern to accomplish the task.
        
        Args:
            initial_message: Initial task description
            
        Returns:
            List of chat messages from the workflow
        """
        await self.initialize()
        
        messages = []
        agents = [
            ("OrchestratorAgent", self.orchestrator_agent),
            ("DevOpsAgent", self.devops_agent),
            ("CodeAnalyzerAgent", self.analyzer_agent),
            ("LoggingAgent", self.logging_agent),
        ]
        
        print("\n🤖 Starting collaborative agent workflow...\n")
        
        # Start with orchestrator getting the initial task
        current_message = initial_message
        iteration = 0
        current_agent_idx = 0
        
        while iteration < self.config.max_iterations:
            iteration += 1
            agent_name, agent = agents[current_agent_idx]
            
            # Run the current agent
            response = await agent.run(current_message)
            response_text = str(response)
            
            messages.append({
                "agent": agent_name,
                "content": response_text
            })
            print(f"[{agent_name}]: {response_text[:300]}...")
            
            # Check for completion signals
            if any(term in response_text.lower() for term in 
                   ["pull request created", "pr created", "workflow complete", "task complete"]):
                print("\n✅ Workflow completed successfully!")
                break
            
            # Determine next agent based on orchestrator's direction or round-robin
            current_message = response_text
            current_agent_idx = (current_agent_idx + 1) % len(agents)
        
        if iteration >= self.config.max_iterations:
            print("\n⚠️ Max iterations reached, stopping workflow.")
        
        return messages
    
    async def _invoke_agent(self, agent: ChatAgent, message: str) -> str:
        """Invoke a single agent and get response"""
        response = await agent.run(message)
        return str(response)


async def main():
    """Main entry point for the orchestration"""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Configuration
    config = OrchestrationConfig(
        workspace_path=os.getenv("WORKSPACE_PATH", "C:/AgentOrchestration/workspace"),
        target_branch="main",
        feature_branch_prefix="feature/add-logging-"
    )
    
    # Create and run orchestration
    orchestration = LoggingEnhancementOrchestration(config)
    
    print("=" * 60)
    print("🚀 Starting Logging Enhancement Orchestration")
    print("=" * 60)
    
    # Option 1: Run sequential workflow (more controlled)
    results = await orchestration.run_sequential_workflow(
        file_patterns=["*.py"]  # Focus on Python files
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 Workflow Summary")
    print("=" * 60)
    print(f"Status: {results['status']}")
    print(f"Started: {results['started_at']}")
    if results.get('completed_at'):
        print(f"Completed: {results['completed_at']}")
    print(f"Steps completed: {len(results['steps'])}")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
