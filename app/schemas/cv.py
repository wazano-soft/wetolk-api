from typing import Literal

from pydantic import BaseModel, Field


class Experience(BaseModel):
    company: str
    role: str
    start_date: str | None = Field(None, description="YYYY-MM")
    end_date: str | None = Field(None, description="YYYY-MM o 'present'")
    location: str | None = None
    description: str | None = None
    achievements: list[str] = []
    technologies: list[str] = []


class Education(BaseModel):
    institution: str
    degree: str
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class Project(BaseModel):
    name: str
    kind: Literal["personal", "research", "innovation"]
    description: str
    technologies: list[str] = []
    url: str | None = None


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    date: str | None = None


class CVExtract(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    degree: str | None = None
    overview: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    skills: list[str] = []
    interests: list[str] = []
    experiences: list[Experience] = []
    education: list[Education] = []
    projects: list[Project] = []
    certifications: list[Certification] = []
    achievements: list[str] = []
    detected_language: Literal["es", "en", "other"] = "es"
