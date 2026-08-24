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


class Suggestion(BaseModel):
    title: str
    description: str
    type: Literal["tip", "question", "improvement", "inconsistency", "other"]
    fix_priority: Literal["low", "medium", "high"]
    fix_suggestion: str | None = None


class CVExtract(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    degree: str | None = None
    overview: str | None = Field(
        None,
        description=(
            "Párrafo de perfil/resumen profesional del candidato -- el texto "
            "introductorio que suele aparecer al inicio del CV bajo encabezados "
            "como 'Perfil', 'Profile', 'Summary', 'About', 'Resumen', etc. "
            "Copiá el texto tal cual aparece bajo esa sección."
        ),
    )
    linkedin_url: str | None = None
    github_url: str | None = None
    youtube_url: str | None = None
    portfolio_url: str | None = None
    skills: list[str] = []
    interests: list[str] = []
    experiences: list[Experience] = []
    education: list[Education] = []
    projects: list[Project] = []
    certifications: list[Certification] = []
    achievements: list[str] = []
    suggestions: list[Suggestion] = Field(
        default_factory=list,
        description=(
            "Análisis generado por vos como experto en reclutamiento/ATS -- esto "
            "NO es texto extraído del CV, es tu evaluación. Completá siempre con "
            "al menos algunas entradas cubriendo las 4 categorías (tip, question, "
            "improvement, inconsistency), salvo que is_risky_prompt sea True."
        ),
    )
    quick_questions: list[str] = []
    detected_language: Literal["es", "en", "other"] = "es"
    is_risky_prompt: bool = False
