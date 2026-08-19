from pydantic import BaseModel, Field

from app.services.llm import get_chat_model

SUGGEST_PROMPT = """A partir de este CV, generá 5 preguntas cortas que un
reclutador o visitante curioso le haría al agente de este candidato. Van a
aparecer como botones en su página pública.

REGLAS:
- Máximo 80 caracteres cada una.
- Concretas, sobre experiencia/skills/proyectos reales del CV de abajo.
- No inventes nada que no esté en el CV.
- Variedad: no repitas el mismo ángulo (ej. no 5 preguntas todas sobre la
  misma tecnología).

CV:
{cv_context}
"""


class QuestionSuggestions(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=5)


def suggest_questions(cv_context: str) -> list[str]:
    model = get_chat_model(temperature=0.5).with_structured_output(QuestionSuggestions)
    result = model.invoke(SUGGEST_PROMPT.format(cv_context=cv_context))
    assert isinstance(result, QuestionSuggestions)
    return [q[:80] for q in result.questions]
