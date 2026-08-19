from app.schemas.cv import CVExtract
from app.services.llm import get_chat_model

EXTRACTION_PROMPT = """Extraé la información del CV al esquema dado.

REGLAS ESTRICTAS:
- Copiá únicamente lo que está escrito en el documento.
- Si un campo no aparece, devolvé null o lista vacía. NUNCA lo inventes.
- No infieras, no estimes, no completes con lo que "suele ir ahí".
- No traduzcas: conservá el idioma original del CV.
- Para fechas ambiguas, usá el formato más específico disponible.

CV:
{cv_text}
"""


def extract_cv(cv_text: str) -> CVExtract:
    model = get_chat_model(temperature=0.0).with_structured_output(CVExtract)
    result = model.invoke(EXTRACTION_PROMPT.format(cv_text=cv_text))
    assert isinstance(result, CVExtract)
    return result
