"""Tests for ask_chat — deterministic memory recall, conversation history
and graceful failure when Ollama is unreachable."""

import pytest


@pytest.fixture
def fast_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)


def offline_chat(**kwargs):
    raise ConnectionError("ollama is down")


class TestDeterministicRecall:
    """These must work even with the model completely unreachable."""

    def test_name_recall_without_model(self, backend, memory_db, monkeypatch):
        monkeypatch.setattr(backend, "chat", offline_chat)
        memory_db.save_memory("identity", "name", "Zakaria")
        assert backend.ask_chat("what is my name") == "Your name is Zakaria."

    def test_name_absent(self, backend, memory_db, monkeypatch):
        monkeypatch.setattr(backend, "chat", offline_chat)
        assert "don't have your name" in backend.ask_chat("what is my name")

    def test_favorite_language_without_model(self, backend, memory_db, monkeypatch):
        monkeypatch.setattr(backend, "chat", offline_chat)
        memory_db.remember_explicit_fact("My favorite programming language is Python")
        reply = backend.ask_chat("What is my favorite programming language?")
        assert reply == "Your favorite programming language is Python."

    def test_forget_and_reforget(self, backend, memory_db, monkeypatch):
        monkeypatch.setattr(backend, "chat", offline_chat)
        memory_db.save_memory("identity", "name", "Zakaria")
        assert backend.ask_chat("forget my name") == "Understood. I have forgotten that memory."
        assert memory_db.get_memory("identity", "name") is None
        assert backend.ask_chat("forget my name") == "I don't have that memory stored."

    def test_what_did_i_say(self, backend, memory_db, monkeypatch):
        monkeypatch.setattr(backend, "chat", offline_chat)
        backend._CHAT_HISTORY.append({"role": "user", "content": "hello there friend"})
        assert backend.ask_chat("what did I say") == "You told me: hello there friend"


class TestConversationFlow:
    def test_success_roundtrip(self, backend, memory_db, monkeypatch):
        monkeypatch.setattr(
            backend,
            "chat",
            lambda **kwargs: {
                "message": {"content": "<think>hmm</think>The answer is 42, sir."}
            },
        )
        reply = backend.ask_chat("What is the meaning of life?")
        assert reply == "The answer is 42, sir."

        # history holds both sides of the exchange
        roles = [m["role"] for m in backend._CHAT_HISTORY]
        assert roles == ["user", "assistant"]

        # and the exchange was persisted to the memory database
        stored = memory_db.load_recent_messages(limit=10)
        assert [m["role"] for m in stored] == ["user", "assistant"]
        assert stored[0]["content"] == "What is the meaning of life?"

    def test_model_failure_is_graceful(self, backend, memory_db, monkeypatch, fast_sleep):
        monkeypatch.setattr(backend, "chat", offline_chat)
        initial_len = len(backend._CHAT_HISTORY)
        reply = backend.ask_chat("tell me something interesting")
        assert reply.startswith("I cannot reach Ollama right now")
        # the failed user message is rolled back from the live history
        assert len(backend._CHAT_HISTORY) == initial_len

    def test_explicit_facts_are_stored_during_chat(self, backend, memory_db, monkeypatch):
        monkeypatch.setattr(
            backend,
            "chat",
            lambda **kwargs: {"message": {"content": "Noted, sir."}},
        )
        backend.ask_chat("My favorite programming language is Rust")
        assert (
            memory_db.get_memory("preference", "favorite_programming_language")
            == "Rust"
        )
