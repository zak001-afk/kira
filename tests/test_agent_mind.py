"""Tests for the agent's own memory: episodes, learnings, fuzzy recall,
reflexion (failures demote a learning so KIRA stops repeating mistakes)."""


class TestEpisodes:
    def test_save_and_recent(self, memory_db):
        memory_db.save_episode(
            "open the notes", "launch the editor",
            {"action": "open_app", "target": "notepad"}, "llm", "success",
        )
        episodes = memory_db.recent_episodes()
        assert len(episodes) == 1
        assert episodes[0]["command"] == "open the notes"
        assert episodes[0]["action"] == {"action": "open_app", "target": "notepad"}
        assert episodes[0]["outcome"] == "success"
        assert episodes[0]["source"] == "llm"

    def test_unknown_outcome_is_coerced(self, memory_db):
        memory_db.save_episode("x", "", {"action": "help"}, "llm", "sideways")
        assert memory_db.recent_episodes()[0]["outcome"] == "unknown"

    def test_clear_episodes(self, memory_db):
        memory_db.save_episode("x", "", {"action": "help"}, "llm", "success")
        assert memory_db.clear_episodes() == 1
        assert memory_db.recent_episodes() == []


class TestLearnings:
    def test_learn_and_recall(self, memory_db):
        memory_db.learn_from_outcome(
            "tickle the engine", {"action": "open_app", "target": "calc"}, True
        )
        recalled = memory_db.recall_action("tickle the engine")
        assert recalled is not None
        assert recalled["action"] == {"action": "open_app", "target": "calc"}
        assert recalled["success_count"] == 1

    def test_recall_requires_successes_to_dominate(self, memory_db):
        memory_db.learn_from_outcome("x task", {"action": "mute"}, True)
        memory_db.learn_from_outcome("x task", {"action": "mute"}, False)
        # 1 success, 1 failure → not trustworthy anymore
        assert memory_db.recall_action("x task") is None

    def test_repeated_success_accumulates(self, memory_db):
        for _ in range(3):
            memory_db.learn_from_outcome("y task", {"action": "volume_up"}, True)
        assert memory_db.recall_action("y task")["success_count"] == 3

    def test_unknown_command_recalls_nothing(self, memory_db):
        assert memory_db.recall_action("never seen before") is None

    def test_normalization_matches_variants(self, memory_db):
        memory_db.learn_from_outcome("Open the Notes!", {"action": "open_app"}, True)
        assert memory_db.recall_action("open the notes") is not None

    def test_top_and_clear(self, memory_db):
        memory_db.learn_from_outcome("a task", {"action": "mute"}, True)
        memory_db.learn_from_outcome("b task", {"action": "mute"}, True)
        memory_db.learn_from_outcome("b task", {"action": "mute"}, True)
        top = memory_db.top_learnings()
        assert len(top) == 2
        assert top[0]["command"] == "b task"  # most successes first
        assert memory_db.clear_learnings() == 2
        assert memory_db.top_learnings() == []

    def test_fuzzy_recall(self, memory_db):
        memory_db.learn_from_outcome(
            "open the download folder",
            {"action": "open_folder", "target": "downloads"},
            True,
        )
        similar = memory_db.find_similar_learnings("open download folder please")
        assert similar
        assert similar[0]["action"]["action"] == "open_folder"

    def test_fuzzy_ignores_unrelated(self, memory_db):
        memory_db.learn_from_outcome(
            "open the download folder", {"action": "open_folder"}, True
        )
        assert memory_db.find_similar_learnings("launch the space shuttle") == []
