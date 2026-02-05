"""
Quality Evaluation Models for Agent Responses

Simplified Pydantic models for extracting structured decisions from agents.
Used with response_format for guaranteed JSON output.
"""
from pydantic import BaseModel, Field


class VerifierOutput(BaseModel):
    """Simplified structured output for the Verifier Agent."""
    tests_exist_and_correct: bool = Field(
        description="True if adequate tests exist and pass, False otherwise"
    )
    feedback: str = Field(
        description="Summary of findings and what tests are needed (if any)"
    )


class ReviewerOutput(BaseModel):
    """Simplified structured output for the Reviewer Agent."""
    approved: bool = Field(
        description="True if tests meet quality standards AND pass, False otherwise"
    )
    feedback: str = Field(
        description="Summary of review and any issues found"
    )
