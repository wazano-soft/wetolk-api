from pydantic import BaseModel, Field

from app.services.llm import get_chat_model

SUGGEST_PROMPT = """A partir de este CV, genera 5 preguntas cortas que un
reclutador o visitante curioso le haría al agente de este candidato, todas las
preguntas que generes deberan poder ser contestadas en su totalidad con la información
recabada del CV, ya sea que se tenga la respuesta descrita exactamente o que lo puedas 
resumir/inferir del resto de información del CV. Van a
aparecer como botones en su página pública.

REGLAS:
- Máximo 150 caracteres cada una.
- Concretas, sobre experiencia/skills/proyectos reales/estudios del CV de abajo.
- No inventes nada que no esté en el CV.
- Variedad: no repitas el mismo ángulo (ej. no 5 preguntas todas sobre la
  misma tecnología).
- SIEMPRE en tercera persona: el visitante le pregunta al agente sobre el
  candidato, no le habla directamente a él/ella. Bien: "¿Qué desafíos ha
  enfrentado como líder de equipo?". Mal: "¿Qué desafíos has enfrentado...?".

CV:
{cv_context}
"""


class QuestionSuggestions(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=5)


QUESTION_MAX_LENGTH = 150


def truncate_question(question: str, limit: int = QUESTION_MAX_LENGTH) -> str:
    # Corta en el último espacio antes del límite (nunca a media palabra) y
    # marca el corte con elipsis -- el LLM a veces se pasa del límite pedido
    # en el prompt, y el constraint quick_questions_question_check de la DB
    # igual lo rechazaría sin este resguardo.
    if len(question) <= limit:
        return question
    truncated = question[: limit - 1].rsplit(" ", 1)[0]
    return f"{truncated}…"


def suggest_questions(cv_context: str) -> list[str]:
    model = get_chat_model(temperature=0.2).with_structured_output(QuestionSuggestions)
    result = model.invoke(SUGGEST_PROMPT.format(cv_context=cv_context))
    assert isinstance(result, QuestionSuggestions)
    return [truncate_question(q) for q in result.questions]
