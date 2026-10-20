"""Scratchpad availability follows the visible game screen, including previews."""

import base64
import json
import unittest

import test_genially_export as fixtures


class ScratchpadTest(unittest.TestCase):
    # Reuse the offline HTTPS browser fixture without inheriting its tests.
    setUpClass = classmethod(fixtures.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.GeniallyExportTest.tearDownClass.__func__)
    setUp = fixtures.GeniallyExportTest.setUp
    tearDown = fixtures.GeniallyExportTest.tearDown
    route = fixtures.GeniallyExportTest.route
    open_editor = fixtures.GeniallyExportTest.open_editor
    import_settings = fixtures.GeniallyExportTest.import_settings

    def preview_frame(self):
        frame = self.editor.locator("#preview").element_handle().content_frame()
        frame.locator("#draftToggle").wait_for(state="attached")
        return frame

    def select_game_preview(self):
        self.editor.locator('[data-design-tab="game"]').click()
        frame = self.preview_frame()
        frame.locator("#startOverlay").wait_for(state="hidden")
        return frame

    def assert_available(self, page):
        page.locator("#draftToggle").wait_for(state="visible", timeout=3000)
        self.assertEqual(page.locator("#draftToggle").get_attribute("aria-expanded"), "false")

    def open_and_draw(self, page, mouse):
        page.locator("#draftToggle").click()
        page.locator("#draftPanel").wait_for(state="visible")
        self.assertEqual(page.locator("#draftToggle").get_attribute("aria-expanded"), "true")
        canvas = page.locator("#draftCanvas")
        canvas.scroll_into_view_if_needed()
        box = canvas.bounding_box()
        self.assertIsNotNone(box)
        x, y = box["x"] + 30, box["y"] + 30
        mouse.move(x, y)
        mouse.down()
        mouse.move(x + 70, y + 40, steps=8)
        mouse.up()
        self.assertTrue(canvas.evaluate("""paper => {
            const rgba = paper.getContext('2d').getImageData(0,0,paper.width,paper.height).data;
            return rgba.some((value,index) => index % 4 === 3 && value > 0);
        }"""), "A visible scratchpad must accept real pencil input")

    def test_game_preview_keeps_enabled_scratchpad_after_repeated_rebuilds(self):
        self.open_editor()
        frame = self.select_game_preview()
        self.assertTrue(self.editor.locator("#draftEnabled").is_checked())
        self.assert_available(frame)
        self.open_and_draw(frame, self.editor.mouse)
        for label in ["Подсказка после первого изменения", "Подсказка после второго изменения"]:
            with self.editor.expect_event("framenavigated", predicate=lambda changed: changed == frame):
                self.editor.locator("#cardLabel").fill(label)
            frame.locator("#qtitle").wait_for(state="visible")
            self.assertEqual(frame.locator("#qtitle").inner_text(), label)
            self.assertTrue(self.editor.locator("#draftEnabled").is_checked())
            self.assert_available(frame)
            self.open_and_draw(frame, self.editor.mouse)

    def test_checkbox_and_design_screen_changes_control_scratchpad_visibility(self):
        self.open_editor()
        frame = self.select_game_preview()
        self.assert_available(frame)
        # The settings live in a collapsed details section.
        self.editor.locator("#draftEnabled").evaluate("el => el.closest('details').open = true")
        for enabled in [False, True]:
            with self.editor.expect_event("framenavigated", predicate=lambda changed: changed == frame):
                self.editor.locator("#draftEnabled").set_checked(enabled)
            frame.locator("#draftToggle").wait_for(state="attached")
            frame.locator("#draftToggle").wait_for(state="visible" if enabled else "hidden")
            self.assertEqual(self.editor.evaluate("readSettings().draftEnabled"), enabled)
        for screen, overlay in [("title", "#startOverlay"), ("win", "#winOverlay"), ("lose", "#overOverlay")]:
            frame.locator("#draftToggle").click()
            frame.locator("#draftPanel").wait_for(state="visible")
            self.editor.locator('[data-design-tab="' + screen + '"]').click()
            frame.locator(overlay).wait_for(state="visible")
            frame.locator("#draftToggle").wait_for(state="hidden")
            frame.locator("#draftPanel").wait_for(state="hidden")
            self.editor.locator('[data-design-tab="game"]').click()
            frame.locator(overlay).wait_for(state="hidden")
            self.assert_available(frame)

    def open_game(self, mode, title_enabled):
        self.import_settings({
            "questions": fixtures.QUESTIONS[:1], "sound": False,
            "draftEnabled": True, "showTitlePage": title_enabled,
        })
        page = self.context.new_page()
        if mode == "standalone":
            page.goto(fixtures.ORIGIN + "/embed-host.html")
            page.set_content(self.editor.evaluate("buildGame(false)"))
        else:
            settings = self.editor.evaluate("readSettings()")
            raw = json.dumps(settings, ensure_ascii=False).encode("utf-8")
            encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
            page.goto(fixtures.ORIGIN + "/game-engine.html#c=" + encoded)
        page.locator("#startOverlay").wait_for(state="attached")
        return page

    def test_real_games_show_scratchpad_during_play_and_restore_it_on_replay(self):
        self.open_editor()
        for mode in ["standalone", "engine"]:
            for title_enabled in [True, False]:
                with self.subTest(mode=mode, title=title_enabled):
                    page = self.open_game(mode, title_enabled)
                    if title_enabled:
                        page.locator("#startOverlay").wait_for(state="visible")
                        self.assertTrue(page.locator("#draftToggle").is_hidden())
                        page.locator("#startBtn").click()
                    page.locator("#startOverlay").wait_for(state="hidden")
                    self.assert_available(page)
                    self.open_and_draw(page, page.mouse)
                    page.locator("#draftClose").click()
                    page.get_by_role("button", name="Да ✓", exact=True).click()
                    page.locator("#winOverlay.show").wait_for(state="visible")
                    page.locator("#draftToggle").wait_for(state="hidden")
                    page.locator("#playAgainBtn").click()
                    page.locator("#winOverlay").wait_for(state="hidden")
                    self.assert_available(page)
                    page.locator("#draftToggle").click()
                    page.locator("#draftPanel").wait_for(state="visible")
                    page.close()


if __name__ == "__main__":
    unittest.main()
