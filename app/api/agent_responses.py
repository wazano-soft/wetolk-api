"""Endpoint compatible con Open Responses (openresponses.org) para el
agente público de cada candidato. Vive en paralelo a /chat (contrato SSE
propio, ya probado) -- no lo reemplaza. Mismo motor por debajo
(app.services.agent_turn), dos contratos de request/response distintos.
"""

import json
import uuid
from collections.abc import Generator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.services.agent_prompt import extract_text_from_content
from app.services.agent_turn import prepare_turn, save_assistant_message
from app.services.llm import get_chat_model

router = APIRouter()


class InputTextPart(BaseModel):
    type: Literal["input_text"]
    text: str


class InputMessage(BaseModel):
    type: Literal["message"]
    role: str
    content: list[InputTextPart]


class ResponsesRequest(BaseModel):
    model: str
    input: list[InputMessage]
    stream: bool = False
    previous_response_id: str | None = None
    # tools / tool_choice / truncation / store: aceptados por el spec pero
    # no soportados todavía -- el agente de un candidato no invoca tools.


def _last_user_text(input_items: list[InputMessage]) -> str:
    for item in reversed(input_items):
        if item.role == "user":
            return "".join(part.text for part in item.content if part.type == "input_text")
    raise HTTPException(status_code=400, detail="No user message in `input`")


def _output_message(item_id: str, text: str, status: str = "completed") -> dict[str, Any]:
    return {
        "type": "message",
        "id": item_id,
        "role": "assistant",
        "status": status,
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


@router.post("/{slug}/responses")
def create_response(slug: str, body: ResponsesRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    user_text = _last_user_text(body.input)

    # previous_response_id se mapea 1:1 al token de nuestra conversación --
    # mismo concepto (continuar un hilo previo), dos nombres distintos.
    ctx = prepare_turn(slug, client_ip, user_text, body.previous_response_id)

    response_id = str(ctx.conversation_token)
    item_id = f"msg_{uuid.uuid4().hex[:24]}"

    if not body.stream:
        model = get_chat_model(temperature=0.3)
        result = model.invoke([("system", ctx.system_prompt), ("human", user_text)])
        text = extract_text_from_content(result.content)
        save_assistant_message(ctx.conversation_pk, text)
        return JSONResponse(
            {
                "id": response_id,
                "status": "completed",
                "output": [_output_message(item_id, text)],
            }
        )

    def event_stream() -> Generator[str, None, None]:
        seq = 0

        def emit(event_type: str, data: dict[str, Any]) -> str:
            nonlocal seq
            seq += 1
            payload = {"type": event_type, "sequence_number": seq, **data}
            return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

        yield emit("response.in_progress", {})
        yield emit(
            "response.output_item.added",
            {
                "output_index": 0,
                "item": {
                    "id": item_id,
                    "type": "message",
                    "role": "assistant",
                    "status": "in_progress",
                    "content": [],
                },
            },
        )
        yield emit(
            "response.content_part.added",
            {"item_id": item_id, "content_index": 0, "part": {"type": "output_text", "text": ""}},
        )

        model = get_chat_model(temperature=0.3)
        full_text = ""
        for chunk in model.stream([("system", ctx.system_prompt), ("human", user_text)]):
            token = extract_text_from_content(chunk.content)
            if token:
                full_text += token
                yield emit(
                    "response.output_text.delta",
                    {"item_id": item_id, "content_index": 0, "delta": token},
                )

        save_assistant_message(ctx.conversation_pk, full_text)

        yield emit(
            "response.output_text.done",
            {"item_id": item_id, "content_index": 0, "text": full_text},
        )
        yield emit("response.content_part.done", {"item_id": item_id, "content_index": 0})
        yield emit(
            "response.output_item.done",
            {"output_index": 0, "item": _output_message(item_id, full_text)},
        )
        yield emit("response.completed", {})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
