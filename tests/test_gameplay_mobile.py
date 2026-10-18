"""Regressions for short games and dialogs in narrow viewports.

Run with the existing test suite; all pages use the synthetic HTTPS origin.
"""

import base64
import json
import unittest

import test_genially_export as export_helpers


class GameplayMobileTest(unittest.TestCase):
    GAME_FORMATS = ("standalone", "engine")

    # Reuse the browser/router helpers without inheriting their test methods.
    setUpClass = classmethod(export_helpers.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(export_helpers.GeniallyExportTest.tearDownClass.__func__)
    setUp = export_helpers.GeniallyExportTest.setUp
    tearDown = export_helpers.GeniallyExportTest.tearDown
    route = export_helpers.GeniallyExportTest.route
    open_editor = export_helpers.GeniallyExportTest.open_editor
    import_settings = export_helpers.GeniallyExportTest.import_settings

    def open_game(self, mode, settings):
        self.import_settings(settings)
        page = self.context.new_page()
        if mode == "standalone":
            page.goto(export_helpers.ORIGIN + "/embed-host.html")
            page.set_content(self.editor.evaluate("buildGame(false)"))
        else:
            config = self.editor.evaluate("readSettings()")
            payload = json.dumps(config, ensure_ascii=False).encode("utf-8")
            encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
            page.goto(export_helpers.ORIGIN + "/game-engine.html#c=" + encoded)
        page.locator("#startBtn").wait_for()
        return page

    def assert_reachable(self, page, selector):
        button = page.locator(selector)
        button.scroll_into_view_if_needed()
        bounds = button.bounding_box()
        self.assertIsNotNone(bounds)
        viewport = page.viewport_size
        self.assertGreaterEqual(bounds["x"], 0)
        self.assertGreaterEqual(bounds["y"], 0)
        self.assertLessEqual(bounds["x"] + bounds["width"], viewport["width"] + 1)
        self.assertLessEqual(bounds["y"] + bounds["height"], viewport["height"] + 1)
        self.assertTrue(button.evaluate("""button => {
            const r = button.getBoundingClientRect();
            return button.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
        }"""), selector + " is obscured or clipped")

    def test_single_question_wins_and_can_be_replayed(self):
        self.open_editor()
        for mode in self.GAME_FORMATS:
            with self.subTest(mode=mode):
                page = self.open_game(mode, {"questions": export_helpers.QUESTIONS[:1], "sound": False})
                page.locator("#startBtn").click()
                for replay in range(2):
                    page.get_by_role("button", name="Да ✓", exact=True).click()
                    page.locator("#winOverlay.show").wait_for(state="visible")
                    self.assertIn("✅ 1", page.locator("#winStats").inner_text())
                    self.assertEqual(page.locator("#progPct").inner_text(), "100")
                    if replay == 0:
                        page.locator("#playAgainBtn").click()
                        self.assertEqual(page.locator("#qtext").inner_text(), export_helpers.FIRST_QUESTION)
                page.close()

    def test_portrait_dialogs_and_result_controls_are_reachable(self):
        self.open_editor()
        for mode in self.GAME_FORMATS:
            with self.subTest(mode=mode):
                page = self.open_game(mode, {
                    "questions": export_helpers.QUESTIONS[:1], "sound": False,
                    "startTitle": "Длинное название учебной игры для телефона " * 4,
                    "startText": "Описание правил игры и заданий. " * 30,
                })
                page.set_viewport_size({"width": 390, "height": 844})
                modal = page.locator("#startOverlay .modal")
                bounds = modal.bounding_box()
                self.assertGreaterEqual(bounds["y"], 19)
                self.assertLessEqual(bounds["y"] + bounds["height"], 825)
                self.assertTrue(modal.evaluate("""dialog =>
                    dialog.scrollHeight > dialog.clientHeight &&
                    ["auto", "scroll"].includes(getComputedStyle(dialog).overflowY)
                """), "Long title-page content needs a visible scrollable dialog")
                self.assert_reachable(page, "#startBtn")
                # Geometry of the rope scene remains independent of the dialogs.
                ratio = page.locator("#scene").evaluate("scene => scene.clientWidth / scene.clientHeight")
                self.assertAlmostEqual(ratio, 16 / 9, delta=0.02)
                page.locator("#startBtn").click()
                page.get_by_role("button", name="Да ✓", exact=True).click()
                page.locator("#winOverlay.show").wait_for(state="visible")
                self.assert_reachable(page, "#playAgainBtn")
                page.locator("#playAgainBtn").click()
                for _ in range(3):
                    page.get_by_role("button", name="Нет", exact=True).click()
                page.locator("#overOverlay.show").wait_for(state="visible")
                self.assert_reachable(page, "#restartBtn")
                self.assert_reachable(page, "#goBackBtn")
                page.locator("#goBackBtn").click()
                page.get_by_role("button", name="Да ✓", exact=True).click()
                page.locator("#winOverlay.show").wait_for(state="visible")
                page.locator("#playAgainBtn").click()
                for _ in range(3):
                    page.get_by_role("button", name="Нет", exact=True).click()
                page.locator("#overOverlay.show").wait_for(state="visible")
                page.locator("#restartBtn").click()
                self.assertTrue(page.locator("#overOverlay").is_hidden())
                page.close()

    def test_scrolled_desktop_preview_stays_below_wrapped_header(self):
        self.open_editor()
        for width in [1920, 1440, 1280, 1024]:
            with self.subTest(width=width):
                self.editor.set_viewport_size({"width": width, "height": 900})
                self.editor.evaluate("window.scrollTo(0,600)")
                self.editor.wait_for_function("""() => {
                    const header = document.querySelector('.top').getBoundingClientRect();
                    const preview = document.querySelector('.previewWrap').getBoundingClientRect();
                    return preview.top >= header.bottom + 9;
                }""")
                self.assert_reachable(self.editor, "#refreshPreview")

    def test_mobile_editor_fits_screen_and_preview_can_be_started(self):
        self.editor.set_viewport_size({"width": 390, "height": 844})
        self.open_editor()
        self.assertLessEqual(self.editor.evaluate("document.documentElement.scrollWidth"), 390)
        self.editor.locator("#togglePreviewEdit").click()
        preview = self.editor.frame_locator("#preview")
        preview.locator("#startBtn").click()
        self.assertEqual(preview.locator("#qtext").inner_text(), export_helpers.FIRST_QUESTION)

    def test_scratchpad_labels_match_in_standalone_and_engine(self):
        self.open_editor()
        label = "Мои вычисления </script> ✓"
        for language, custom, expected in [("ru", label, label), ("en", "", "Scratchpad")]:
            for mode in self.GAME_FORMATS:
                with self.subTest(mode=mode, language=language):
                    page = self.open_game(mode, {
                        "questions": export_helpers.QUESTIONS[:1], "sound": False,
                        "draftEnabled": True, "translateInterface": language != "ru",
                        "uiLanguage": language, "theme": {"draftLabel": custom},
                    })
                    page.locator("#startBtn").click()
                    toggle = page.locator("#draftToggle")
                    self.assertIn(expected, toggle.inner_text())
                    toggle.click()
                    self.assertEqual(page.locator(".draftHead span").inner_text(), expected)
                    self.assertEqual(page.locator("#draftPanel").get_attribute("aria-label"), expected)
                    page.locator("#draftClose").click()
                    self.assertIn(expected, toggle.inner_text())
                    page.close()


if __name__ == "__main__":
    unittest.main()
