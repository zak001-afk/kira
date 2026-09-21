"""Self-awareness: memory analytics, systems check, daily review, habit hints."""
from datetime import datetime

import kira_thought


class TestMemoryAnalytics:
    def test_episode_counts_and_summary(self, memory_db):
        memory_db.save_episode("open chrome", "t", {"action": "open_app"}, "parser", "success")
        memory_db.save_episode("open chrome", "t", {"action": "open_app"}, "parser", "success")
        memory_db.save_episode("click it", "t", {"action": "click"}, "llm", "failed")
        counts = memory_db.episode_counts()
        assert counts == {"total": 3, "success": 2, "failed": 1}
        memory_db.learn_from_outcome("open chrome", {"action": "open_app"}, True)
        summary = memory_db.learnings_summary()
        assert summary["count"] == 1 and summary["uses"] == 1

    def test_counts_survive_an_empty_database(self, memory_db):
        assert memory_db.episode_counts() == {"total": 0, "success": 0, "failed": 0}
        assert memory_db.learnings_summary()["count"] == 0

    def test_episodes_on_filters_by_day(self, memory_db):
        memory_db.save_episode("do a thing", "", {"action": "mute"}, "llm", "success")
        today = datetime.now().date().isoformat()
        assert len(memory_db.episodes_on(today)) == 1
        assert memory_db.episodes_on("1999-01-01") == []

    def test_successful_episode_hours_pairs_command_with_hour(self, memory_db):
        memory_db.save_episode("open vscode", "", {"action": "open_app"}, "llm", "success")
        memory_db.save_episode("click it", "", {"action": "click"}, "llm", "failed")
        pairs = memory_db.successful_episode_hours()
        assert len(pairs) == 1
        command, hour = pairs[0]
        assert command == "open vscode"
        assert 0 <= hour <= 23


class TestSelfReport:
    def test_reports_counts_and_uptime(self, memory_db):
        memory_db.save_episode("a", "", {"action": "mute"}, "llm", "success")
        memory_db.save_episode("b", "", {"action": "mute"}, "llm", "failed")
        memory_db.learn_from_outcome("a", {"action": "mute"}, True)
        memory_db.save_memory("identity", "name", "zakaria")
        text = kira_thought.self_report(models_online=True)
        assert "All systems nominal" in text
        assert "50% success rate" in text
        assert "1 learned skills" in text
        assert "Local models responding normally" in text

    def test_reports_model_outage_gracefully(self, memory_db):
        text = kira_thought.self_report(models_online=False)
        assert "unreachable" in text

    def test_french_and_arabic(self, memory_db):
        assert "systèmes" in kira_thought.self_report(language="fr")
        assert "الأنظمة" in kira_thought.self_report(language="ar")


class TestSelfReview:
    def test_quiet_day_message(self, memory_db):
        assert "quiet day" in kira_thought.self_review()
        assert "journée calme" in kira_thought.self_review(language="fr")

    def test_review_rates_the_day_and_names_failures(self, memory_db):
        memory_db.save_episode("open chrome", "", {"action": "open_app"}, "llm", "success")
        memory_db.save_episode("click the icon", "", {"action": "click"}, "llm", "failed")
        text = kira_thought.self_review()
        assert "2 operations" in text
        assert "click the icon" in text
        assert "demoted" in text.lower()

    def test_perfect_day_changes_tone(self, memory_db):
        memory_db.save_episode("open chrome", "", {"action": "open_app"}, "llm", "success")
        text = kira_thought.self_review()
        assert "clean sheet" in text

    def test_review_languages(self, memory_db):
        memory_db.save_episode("open chrome", "", {"action": "open_app"}, "llm", "success")
        assert "Bilan du jour" in kira_thought.self_review(language="fr")
        assert "مراجعة اليوم" in kira_thought.self_review(language="ar")


class TestHabitHint:
    def _seed_hours(self, memory_db, command, hour, times):
        # episodes are stamped "now"; the pure hint takes an hour argument
        for _ in range(times):
            memory_db.save_episode(command, "", {"action": "open_app"}, "llm", "success")
        return hour

    def test_no_history(self, memory_db):
        assert "enough history" in kira_thought.habit_hint()

    def test_habit_needs_at_least_three_uses(self, memory_db):
        self._seed_hours(memory_db, "open spotify", datetime.now().hour, 2)
        assert "No clear habit" in kira_thought.habit_hint()

    def test_detects_habit_at_this_hour(self, memory_db):
        now_hour = datetime.now().hour
        self._seed_hours(memory_db, "open spotify", now_hour, 4)
        text = kira_thought.habit_hint()
        assert "open spotify" in text
        assert "Pattern detected" in text

    def test_no_habit_for_unrelated_hour(self, memory_db):
        self._seed_hours(memory_db, "open spotify", datetime.now().hour, 4)
        distant = (datetime.now().hour + 12) % 24
        text = kira_thought.habit_hint(hour=distant)
        assert "No clear habit" in text

    def test_localized(self, memory_db):
        self._seed_hours(memory_db, "open spotify", datetime.now().hour, 4)
        assert "Habitude repérée" in kira_thought.habit_hint(language="fr")
        assert "لاحظت نمطاً" in kira_thought.habit_hint(language="ar")


class TestBackendSelfCommands:
    def test_system_check_reaches_the_model(self, backend, memory_db, speak_silenced):
        # stubbed ollama raises → KIRA honestly reports model unavailability
        reply = backend.execute_action({"action": "self_report", "language": "en"})
        assert "All systems nominal" in reply
        assert "unreachable" in reply

    def test_self_review_and_habit_hint_execute(self, backend, memory_db, speak_silenced):
        assert "quiet day" in backend.execute_action(
            {"action": "self_review", "language": "en"}
        )
        assert "history" in backend.execute_action(
            {"action": "habit_hint", "language": "en"}
        )

    def test_parser_routes_the_mind_commands(self, backend):
        assert backend.parse_simple_command("systems check")["action"] == "self_report"
        assert backend.parse_simple_command("how are you feeling")["action"] == (
            "self_report"
        )
        assert backend.parse_simple_command("review your day")["action"] == "self_review"
        assert backend.parse_simple_command("what do i usually do now")["action"] == (
            "habit_hint"
        )
