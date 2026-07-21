import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

import backend.routers.chat as chat_router
from backend.contracts.schemas import ChatRequest
from backend.infra.db.conversation_storage import ConversationStorage


pytestmark = pytest.mark.unit


def test_sync_chat_passes_override_and_attachments(monkeypatch):
    captured = None

    def fake_run_chat(*args):
        nonlocal captured
        captured = args
        return {"response": "ok", "rag_trace": None}

    monkeypatch.setattr(chat_router, "run_chat", fake_run_chat)
    response = asyncio.run(chat_router.chat_endpoint(
        ChatRequest(
            message="compare",
            session_id="session",
            context_files=["manual.pdf"],
            force_comprehensive=True,
        ),
        current_user=SimpleNamespace(username="user"),
    ))

    assert response.response == "ok"
    assert captured == ("compare", "user", "session", ["manual.pdf"], True)


def test_stream_chat_passes_default_false_to_optional_path(monkeypatch):
    captured = None

    async def fake_run_chat_stream(*args):
        nonlocal captured
        captured = args
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(chat_router, "run_chat_stream", fake_run_chat_stream)

    async def consume():
        response = await chat_router.chat_stream_endpoint(
            ChatRequest(message="hello", session_id="session"),
            current_user=SimpleNamespace(username="user"),
        )
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(consume())

    assert chunks
    assert captured == ("hello", "user", "session", False, [], False)


def test_user_message_request_mode_round_trips_storage_contract():
    serialized = ConversationStorage._serialize_message(
        HumanMessage(content="compare"),
        datetime(2026, 7, 21),
        {"force_comprehensive": True},
    )
    restored = ConversationStorage._to_langchain_messages([serialized])[0]

    assert serialized["rag_trace"] is None
    assert serialized["force_comprehensive"] is True
    assert restored.additional_kwargs["force_comprehensive"] is True
