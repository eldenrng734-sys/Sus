from typing import Literal

from pydantic import BaseModel, Field


class AIAssessmentOutput(BaseModel):
    """The fixed form the LLM must fill in. Our code validates it."""

    category: Literal[
        "individual_customer", "business_customer", "partner", "other"
    ]
    intent: Literal[
        "request_demo", "pricing", "support", "info_request", "complaint", "other"
    ]
    interest: str = Field(max_length=200)
    buying_stage: Literal["awareness", "consideration", "decision", "unknown"]
    sentiment: Literal["positive", "neutral", "negative"]
    priority: Literal["low", "medium", "high"]
    lead_score: int = Field(ge=0, le=100)
    recommended_action: Literal[
        "schedule_demo", "call", "email", "follow_up", "none"
    ]
    follow_up_days: int = Field(ge=0, le=90)
    confidence: float = Field(ge=0.0, le=1.0)