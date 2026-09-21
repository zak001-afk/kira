"""Tests for kira_thought — the think → act → reflect loop."""

import pytest

import kira_thought
import kira_memory


@pytest.fixture(autouse=True)
def clean_mind(memory_db):
    return memory_db


def ollama_returning(payload):
    def _fn(messages, options=None):
        return {"message": {"content": payload}}

    return _fn


def ollama_exploding(messages, options=None):
    raise ConnectionError("ollama is down")


class TestValidateAction:
    def test_accepts_known_actions(self):
        assert kira_thought.validate_action({"action": "open_app", "target": "x"})
        assert kira_thought.validate_action({"action": "none"})

    def test_rejects_unknown_actions(self):
        assert not kira_thought.validate_action({"action": "format_disk"})
        assert not kira_thought.validate_action({"action": ""})
        assert not kira_thought.validate_action("open_chrome")
        assert not kira_thought.validate_action(None)

    def test_sequences_checked_recursively(self):
        good = {
            "action": "sequence",
            "steps": [
                {"action": "open_app", "target": "a"},
                {"action": "search", "query": "b"},
            ],
        }
        bad = {
            "action": "sequence",
            "steps": [{"action": "delete_everything"}],
        }
        nested = {
            "action": "sequence",
            "steps": [{"action": "sequence", "steps": [{"action": "mute"}]}],
        }
        assert kira_thought.validate_action(good)
        assert not kira_thought.validate_action(bad)
        assert not kira_thought.validate_action(nested)
        assert not kira_thought.validate_action({"action": "sequence", "steps": []})


class TestThinkRecall:
    def test_memory_hit_does_not_call_the_model(self):
        kira_memory.learn_from_outcome(
            "spin the flux capacitor", {"action": "mute"}, True
        )

        def should_not_be_called(messages, options=None):
            raise AssertionError("the model must not be consulted on a recall")

        thought = kira_thought.think("spin the flux capacitor", should_not_be_called)
        assert thought.source == "memory"
        assert thought.action == {"action": "mute"}
        assert "done this before" in thought.text
        assert kira_thought.last_thought() is thought

    def test_similarity_recall(self):
        kira_memory.learn_from_outcome(
            "open the project folder", {"action": "open_folder", "target": "projects"}, True
        )
        thought = kira_thought.think("open project folder", ollama_exploding)
        assert thought.source == "memory"
        assert thought.action["action"] == "open_folder"
        assert "resembles" in thought.text


class TestThinkWithModel:
    def test_envelope_parse(self):
        payload = '{"thought": "user wants the editor", "action": {"action": "open_app", "target": "code"}}'
        thought = kira_thought.think("fire up my editor", ollama_returning(payload))
        assert thought.source == "llm"
        assert thought.text == "user wants the editor"
        assert thought.action == {"action": "open_app", "target": "code"}

    def test_legacy_direct_action_gets_fallback_thought(self):
        payload = '{"action": "volume_up"}'
        thought = kira_thought.think("crank it up", ollama_returning(payload))
        assert thought.source == "llm"
        assert thought.action == {"action": "volume_up"}
        assert thought.text == "Here is what I intend to do."

    def test_invalid_action_rejected(self):
        payload = '{"thought": "time to destroy", "action": {"action": "format_disk"}}'
        thought = kira_thought.think("wipe my disk", ollama_returning(payload))
        assert thought.source == "invalid"
        assert thought.action == {"action": "none"}

    def test_model_garbage_handled(self):
        thought = kira_thought.think("blorf", ollama_returning("I have no idea"))
        assert thought.source == "invalid"
        assert thought.action == {"action": "none"}

    def test_model_outage_handled(self):
        thought = kira_thought.think("do anything", ollama_exploding)
        assert thought.source == "invalid"
        assert thought.action == {"action": "none"}
        assert "cannot reach my reasoning model" in thought.text


class TestReflect:
    def test_success_records_episode_and_learning(self):
        action = {"action": "open_app", "target": "paint"}
        kira_thought.reflect("doodle something", action, "llm", "success")
        episodes = kira_memory.recent_episodes()
        assert len(episodes) == 1
        assert episodes[0]["outcome"] == "success"
        assert kira_memory.recall_action("doodle something")["action"] == action

    def test_failure_demotes_learning(self):
        kira_thought.reflect(
            "jam the printer", {"action": "open_app", "target": "x"}, "llm", "failed"
        )
        # only failures on record → recall refuses it (reflexion)
        assert kira_memory.recall_action("jam the printer") is None

    def test_failure_after_success_breaks_tie_against_reuse(self):
        action = {"action": "open_app", "target": "x"}
        kira_thought.reflect("risky move", action, "llm", "success")
        assert kira_memory.recall_action("risky move") is not None
        kira_thought.reflect("risky move", action, "memory", "failed")
        assert kira_memory.recall_action("risky move") is None

    def test_episode_carries_the_thought_text(self):
        payload = '{"thought": "user wants music stopped", "action": {"action": "mute"}}'
        kira_thought.think("silence the noise please", ollama_returning(payload))
        kira_thought.reflect(
            "silence the noise please", {"action": "mute"}, "llm", "success"
        )
        episode = kira_memory.recent_episodes()[0]
        assert episode["thought"] == "user wants music stopped"

    def test_reflect_guards_against_nonsense(self):
        kira_thought.reflect("x", None, "llm", "success")
        kira_thought.reflect("x", {"action": "none"}, "llm", "success")
        assert kira_memory.recent_episodes() == []

    def test_parser_actions_are_not_learned(self):
        # deterministic parser decisions don't belong in the learning table
        kira_thought.reflect("mute", {"action": "mute"}, "parser", "success")
        assert kira_memory.recent_episodes() != []  # episode still logged
        assert kira_memory.recall_action("mute") is None  # but nothing learned


class TestMindReports:
    def test_describe_empty(self):
        assert "not learned" in kira_thought.describe_learnings(language="en")
        assert "aucune" in kira_thought.describe_learnings(language="fr")
        assert "سيدي" in kira_thought.describe_learnings(language="ar")

    def test_describe_with_entries(self):
        kira_memory.learn_from_outcome("tickle the engine", {"action": "mute"}, True)
        description = kira_thought.describe_learnings(language="en")
        assert "tickle the engine" in description
        assert "mute" in description

    def test_cleared_message(self):
        assert kira_thought.cleared_message(0, "en") == kira_thought.describe_learnings(language="en")
        assert kira_thought.cleared_message(3, "en") == "Done sir. I have forgotten all 3 learned commands."


class TestBackendIntegration:
    """End-to-end through the real backend: it plans, acts, learns, recalls."""

    def test_second_identical_command_uses_memory(self, backend, memory_db, monkeypatch):
        command = "spin the flux capacitor"
        payload = '{"thought": "user wants silence", "action": {"action": "mute"}}'
        monkeypatch.setattr(backend, "chat", lambda **kw: {"message": {"content": payload}})

        # parse misses this command → plan → execute (stub) → learn
        assert backend.parse_simple_command(command) is None
        thought = backend.think_about(command)
        assert thought.source == "llm"
        assert backend.execute_action(thought.action) is True
        backend.learn_from(command, thought.action, thought.source, True)

        # second time: the model is "down", yet KIRA still knows what to do
        def down(**kw):
            raise ConnectionError("ollama down")

        monkeypatch.setattr(backend, "chat", down)
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        again = backend.think_about(command)
        assert again.source == "memory"
        assert again.action == {"action": "mute"}
        assert backend.execute_action(again.action) is True

    def test_agent_mind_commands(self, backend, memory_db):
        assert backend.parse_simple_command("what did you learn")["action"] == "agent_learnings"
        assert backend.parse_simple_command("qu'as-tu appris")["action"] == "agent_learnings"
        assert backend.parse_simple_command("ماذا تعلمت")["action"] == "agent_learnings"
        assert backend.parse_simple_command("forget what you learned")["action"] == "agent_forget"
        assert backend.parse_simple_command("انس ما تعلمته")["action"] == "agent_forget"

    def test_agent_learnings_spoken_reports(self, backend, memory_db):
        reply = backend.execute_action({"action": "agent_learnings", "language": "en"})
        assert "not learned" in reply

        kira_memory.learn_from_outcome("do a handstand", {"action": "mute"}, True)
        reply = backend.execute_action({"action": "agent_learnings", "language": "en"})
        assert "do a handstand" in reply

        cleared = backend.execute_action({"action": "agent_forget", "language": "en"})
        assert "1 learned command" in cleared
        assert kira_memory.top_learnings() == []
