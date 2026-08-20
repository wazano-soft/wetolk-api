from typing import Literal

from pydantic import BaseModel, Field


class SearchCriteria(BaseModel):
    role: str | None = None
    seniority: str | None = None
    location: str | None = None
    work_mode: Literal["remote", "hybrid", "onsite"] | None = None
    skills: list[str] = []
    years_min: float | None = None


class CandidateMatch(BaseModel):
    highlights: list[str]
    score: int = Field(ge=0, le=100)
    justification: str
