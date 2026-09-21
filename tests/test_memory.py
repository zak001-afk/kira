"""Tests for kira_memory — the SQLite-backed long-term memory."""


class TestMemoryCRUD:
    def test_roundtrip(self, memory_db):
        assert memory_db.get_memory("preference", "drink") is None
        assert memory_db.save_memory("preference", "drink", "mint tea")
        assert memory_db.get_memory("preference", "drink") == "mint tea"

    def test_upsert_overwrites(self, memory_db):
        memory_db.save_memory("preference", "drink", "tea")
        memory_db.save_memory("preference", "drink", "coffee")
        assert memory_db.get_memory("preference", "drink") == "coffee"

    def test_empty_fields_rejected(self, memory_db):
        assert not memory_db.save_memory("", "k", "v")
        assert not memory_db.save_memory("c", "", "v")
        assert not memory_db.save_memory("c", "k", "  ")

    def test_forget(self, memory_db):
        memory_db.save_memory("identity", "name", "zak")
        assert memory_db.forget_memory("identity", "name")
        assert not memory_db.forget_memory("identity", "name")
        assert memory_db.get_memory("identity", "name") is None

    def test_memory_exists(self, memory_db):
        memory_db.save_memory("a", "b", "c")
        assert memory_db.memory_exists("a", "b")
        assert not memory_db.memory_exists("a", "nope")

    def test_update_memory(self, memory_db):
        assert memory_db.update_memory("pref", "theme", "dark")
        assert memory_db.get_memory("pref", "theme") == "dark"

    def test_load_memories_filter_by_category(self, memory_db):
        memory_db.save_memory("identity", "name", "zak")
        memory_db.save_memory("preference", "drink", "tea")
        grouped = memory_db.load_memories("identity")
        assert [m["key"] for m in grouped] == ["name"]
        assert len(memory_db.load_memories()) == 2


class TestConversations:
    def test_messages_are_stored_and_ordered(self, memory_db):
        session = memory_db.new_session_id()
        memory_db.save_message(session, "user", "hello")
        memory_db.save_message(session, "assistant", "hi sir")
        messages = memory_db.load_recent_messages(limit=10)
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "hello"

    def test_limit_returns_most_recent(self, memory_db):
        session = memory_db.new_session_id()
        for i in range(20):
            memory_db.save_message(session, "user", f"message {i}")
        messages = memory_db.load_recent_messages(limit=5)
        assert len(messages) == 5
        assert messages[-1]["content"] == "message 19"
        assert messages[0]["content"] == "message 15"

    def test_empty_message_ignored(self, memory_db):
        memory_db.save_message("s", "user", "   ")
        assert memory_db.load_recent_messages() == []

    def test_search_messages(self, memory_db):
        session = memory_db.new_session_id()
        memory_db.save_message(session, "user", "I love python programming")
        memory_db.save_message(session, "user", "unrelated small talk")
        hits = memory_db.search_messages("python")
        assert len(hits) == 1
        assert hits[0]["content"] == "I love python programming"

    def test_search_ignores_short_words(self, memory_db):
        memory_db.save_message("s", "user", "my ai assistant")
        assert memory_db.search_messages("ai") == []

    def test_session_ids_are_unique(self, memory_db):
        assert memory_db.new_session_id() != memory_db.new_session_id()


class TestExplicitFacts:
    def test_favorite_language(self, memory_db):
        memory_db.remember_explicit_fact("My favorite programming language is Python")
        assert (
            memory_db.get_memory("preference", "favorite_programming_language")
            == "Python"
        )

    def test_name(self, memory_db):
        memory_db.remember_explicit_fact("My name is Zakaria")
        assert memory_db.get_memory("identity", "name") == "Zakaria"

    def test_non_fact_is_not_stored(self, memory_db):
        memory_db.remember_explicit_fact("open chrome")
        assert memory_db.load_memories() == []
