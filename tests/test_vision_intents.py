"""Tests for the screen-understanding intent detection and target extraction
used by the vision click loop — these run before any model is called."""


class TestIsVisionRequest:
    def test_direct_screen_questions(self, backend):
        assert backend.is_vision_request("what's on my screen")
        assert backend.is_vision_request("what is on my screen")
        assert backend.is_vision_request("analyze my screen")
        assert backend.is_vision_request("analyse mon écran")

    def test_find_requires_screen_context(self, backend):
        assert backend.is_vision_request("find the save button on my screen")
        # "locate" without screen context is not a vision request
        assert not backend.is_vision_request("locate the start button")

    def test_plain_command_is_not_a_vision_request(self, backend):
        assert not backend.is_vision_request("open chrome")
        assert not backend.is_vision_request("")


class TestIsVisionClickRequest:
    def test_find_and_click(self, backend):
        assert backend.is_vision_click_request("find the save button and click it")

    def test_french_find_and_click(self, backend):
        assert backend.is_vision_click_request("trouve le bouton et clique dessus")

    def test_find_without_click_is_not_a_click_request(self, backend):
        assert not backend.is_vision_click_request("find the save button on my screen")

    def test_plain_click_is_not_a_vision_click(self, backend):
        assert not backend.is_vision_click_request("click")


class TestExtractVisionTarget:
    def test_english_on_screen(self, backend):
        assert (
            backend._extract_vision_target("find the save button on my screen")
            == "save button"
        )

    def test_english_and_click(self, backend):
        assert (
            backend._extract_vision_target("locate the Start menu and click it")
            == "Start menu"
        )

    def test_french(self, backend):
        assert (
            backend._extract_vision_target("trouve le bouton enregistrer sur mon écran")
            == "bouton enregistrer"
        )

    def test_no_target(self, backend):
        assert backend._extract_vision_target("hello there") == ""
