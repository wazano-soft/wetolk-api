from app.schemas.search import CandidateMatch, SearchCriteria
from app.services.llm import get_chat_model

CRITERIA_PROMPT = """Extraé los criterios de búsqueda de esta descripción de puesto en
lenguaje natural, al esquema dado.

REGLAS:
- Copia únicamente lo que está implícito o explícito en el texto.
- Si un criterio no aparece, devoluelve null o lista vacía. No lo inventes.
- years_min es el mínimo de años de experiencia pedido, si se menciona.

Búsqueda: {query}
"""


def extract_search_criteria(query: str) -> SearchCriteria:
    model = get_chat_model(temperature=0.0).with_structured_output(SearchCriteria)
    result = model.invoke(CRITERIA_PROMPT.format(query=query))
    assert isinstance(result, SearchCriteria)
    return result


MATCH_PROMPT = """Un reclutador busca: "{query}"

Este es el perfil de un candidato (en tercera persona, no le atribuyas nada que
no esté acá):
{cv_context}

Genera, al esquema dado:
- highlights: hasta 5 frases cortas y concretas de por qué este perfil calza
  con la búsqueda, basadas ÚNICAMENTE en la información de arriba. Nunca
  inventes experiencia, tecnologías ni logros que no estén.
- score: 0 a 100, qué tan bien matchea el perfil con la búsqueda.
- justification: una sola línea explicando el score.
"""


def generate_match(query: str, cv_context: str) -> CandidateMatch:
    model = get_chat_model(temperature=0.1).with_structured_output(CandidateMatch)
    result = model.invoke(MATCH_PROMPT.format(query=query, cv_context=cv_context))
    assert isinstance(result, CandidateMatch)
    return result
