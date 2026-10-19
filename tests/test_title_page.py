"""Browser regressions for the optional title page in preview and exports."""

import base64
import json
import unittest

import test_genially_export as fixtures


class TitlePageTest(unittest.TestCase):
    # Reuse the offline HTTPS fixture without inheriting its test methods.
    setUpClass = classmethod(fixtures.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.GeniallyExportTest.tearDownClass.__func__)
    setUp = fixtures.GeniallyExportTest.setUp
    tearDown = fixtures.GeniallyExportTest.tearDown
    route = fixtures.GeniallyExportTest.route
    open_editor = fixtures.GeniallyExportTest.open_editor
    import_settings = fixtures.GeniallyExportTest.import_settings

    def preview_frame(self):
        frame = self.editor.locator("#preview").element_handle().content_frame()
        frame.locator("#startOverlay").wait_for(state="attached")
        return frame

    def select_title(self):
        self.editor.locator('[data-design-tab="title"]').click()

    def switch_title(self, enabled):
        frame = self.preview_frame()
        with self.editor.expect_event("framenavigated", predicate=lambda changed: changed == frame):
            self.editor.locator("#showTitlePage").set_checked(enabled)
        frame.locator("#startOverlay").wait_for(state="visible" if enabled else "hidden")
        self.assertEqual(self.editor.evaluate("readSettings().showTitlePage"), enabled)
        return frame

    def assert_game_preview(self, frame):
        frame.locator("#startOverlay").wait_for(state="hidden")
        frame.wait_for_function("""expected =>
            document.querySelectorAll('.overlay.show').length === 0 &&
            document.querySelector('#qtext').textContent === expected
        """, arg=fixtures.FIRST_QUESTION, polling=100)
        self.assertTrue(frame.locator(".scene").is_visible())

    def test_disabling_title_hides_it_despite_selected_tab_and_other_title_edits(self):
        self.open_editor()
        self.select_title()
        frame = self.preview_frame()
        frame.locator("#startOverlay").wait_for(state="visible")
        self.switch_title(False)
        self.assert_game_preview(frame)

        with self.editor.expect_event("framenavigated", predicate=lambda changed: changed == frame):
            self.editor.locator("#startTitle").fill("Заголовок выключенной заставки")
        self.assert_game_preview(frame)

        # Changing tabs must not force a disabled title page back into view.
        self.editor.locator('[data-design-tab="lose"]').click()
        frame.locator("#overOverlay").wait_for(state="visible")
        self.select_title()
        self.assert_game_preview(frame)
        self.switch_title(True)
        self.assertIn("Заголовок выключенной заставки", frame.locator("#startOverlay h1").inner_text())

    def test_disabled_title_stays_disabled_after_reload_and_project_import(self):
        self.open_editor()
        self.select_title()
        self.switch_title(False)
        self.editor.reload()
        self.editor.wait_for_function("typeof readSettings === 'function' && !readSettings().showTitlePage")
        self.assertFalse(self.editor.locator("#showTitlePage").is_checked())
        frame = self.preview_frame()
        self.assert_game_preview(frame)
        self.select_title()
        self.assert_game_preview(frame)

        self.import_settings({"showTitlePage": True})
        frame.locator("#startOverlay").wait_for(state="visible")
        self.import_settings({"showTitlePage": False})
        self.assertFalse(self.editor.locator("#showTitlePage").is_checked())
        self.assert_game_preview(frame)

    def test_undo_and_redo_of_title_checkbox_restore_visible_state(self):
        self.open_editor()
        self.select_title()
        frame = self.switch_title(False)
        self.editor.locator("#undoEdit").click()
        frame.locator("#startOverlay").wait_for(state="visible")
        self.assertTrue(self.editor.locator("#showTitlePage").is_checked())
        self.editor.locator("#redoEdit").click()
        self.assertFalse(self.editor.locator("#showTitlePage").is_checked())
        self.assert_game_preview(frame)

    @staticmethod
    def release_font_requests(held):
        while held:
            held.pop().abort()

    def test_disabled_title_does_not_return_while_fonts_delay_preview_bootstrap(self):
        self.open_editor()
        self.select_title()
        frame = self.preview_frame()
        frame.locator("#startOverlay").wait_for(state="visible")
        held = []
        hold = lambda route: held.append(route)
        self.context.route("https://fonts.googleapis.com/**", hold)
        try:
            with self.editor.expect_request(lambda request: request.url.startswith("https://fonts.googleapis.com/")):
                self.editor.locator("#showTitlePage").uncheck()
            frame.locator("#startOverlay").wait_for(state="attached")
            self.assertTrue(held, "The fixture must delay the rebuilt iframe's font stylesheets")
            for _ in range(6):
                self.assertFalse(self.editor.locator("#showTitlePage").is_checked())
                self.assertFalse(frame.locator("#startOverlay").is_visible(),
                                 "Disabled title must stay hidden before the game bootstrap can execute")
                self.editor.wait_for_timeout(500)
            self.release_font_requests(held)
            self.assert_game_preview(frame)
            for sample in range(14):
                if sample == 4:
                    self.editor.locator("#togglePreviewEdit").click()
                elif sample == 8:
                    self.editor.set_viewport_size({"width": 1360, "height": 900})
                elif sample == 10:
                    self.editor.locator("#togglePreviewEdit").click()
                self.assertFalse(self.editor.locator("#showTitlePage").is_checked())
                self.assertFalse(self.editor.evaluate("readSettings().showTitlePage"))
                self.assertFalse(frame.locator("#startOverlay").is_visible())
                self.editor.wait_for_timeout(500)
        finally:
            self.context.unroute("https://fonts.googleapis.com/**", hold)
            self.release_font_requests(held)

    def test_export_initial_title_visibility_is_correct_before_slow_fonts_finish(self):
        self.open_editor()
        for mode in ["standalone", "engine"]:
            for enabled in [False, True]:
                with self.subTest(mode=mode, enabled=enabled):
                    self.import_settings({
                        "showTitlePage": enabled, "questions": fixtures.QUESTIONS[:1],
                        "shuffleQuestions": False, "sound": False,
                    })
                    page = self.context.new_page()
                    held = []
                    page.route("https://fonts.googleapis.com/**", lambda route: held.append(route))
                    try:
                        if mode == "standalone":
                            html = self.editor.evaluate("buildGame(false)")
                            page.goto(fixtures.ORIGIN + "/embed-host.html")
                            # Schedule document.write so Playwright can inspect
                            # the parsed markup while the bootstrap is blocked.
                            page.evaluate("""html => setTimeout(() => {
                                document.open(); document.write(html); document.close();
                            }, 0)""", html)
                        else:
                            settings = self.editor.evaluate("readSettings()")
                            payload = json.dumps(settings, ensure_ascii=False).encode("utf-8")
                            encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
                            page.goto(fixtures.ORIGIN + "/game-engine.html#c=" + encoded, wait_until="commit")
                        if mode == "standalone":
                            page.locator("#startOverlay").wait_for(state="attached")
                            self.assertTrue(held, "The exported game's font stylesheets must remain pending")
                            self.assertIsNone(page.locator("#charGif").get_attribute("data-pose"),
                                              "Inspect initial HTML before bootstrap, not its corrected state")
                            self.assertEqual(page.locator("#startOverlay").is_visible(), enabled)
                            page.wait_for_timeout(500)
                            self.assertEqual(page.locator("#startOverlay").is_visible(), enabled)
                        else:
                            # Engine document.write can stop the parser at its
                            # stylesheet before body is available. Absence of
                            # the overlay is a valid hidden loading state.
                            page.wait_for_function("document.querySelector('link[rel=stylesheet]')", polling=100)
                            page.wait_for_timeout(500)
                            self.assertTrue(held, "Engine font stylesheets must remain pending")
                            if not enabled:
                                self.assertEqual(page.locator("#startOverlay.show").count(), 0)
                        self.release_font_requests(held)
                        page.locator("#startOverlay").wait_for(state="attached")
                        page.wait_for_load_state("load")
                        page.wait_for_function("document.querySelector('#charGif').dataset.pose === 'stand'", polling=100)
                        self.assertEqual(page.locator("#startOverlay").is_visible(), enabled)
                        if not enabled:
                            self.assertEqual(page.locator("#qtext").inner_text(), fixtures.FIRST_QUESTION)
                    finally:
                        self.release_font_requests(held)
                        page.close()

    def open_game(self, mode, enabled):
        self.import_settings({
            "showTitlePage": enabled, "questions": fixtures.QUESTIONS[:1],
            "shuffleQuestions": False, "sound": False,
        })
        page = self.context.new_page()
        if mode == "standalone":
            page.goto(fixtures.ORIGIN + "/embed-host.html")
            page.set_content(self.editor.evaluate("buildGame(false)"))
        else:
            settings = self.editor.evaluate("readSettings()")
            payload = json.dumps(settings, ensure_ascii=False).encode("utf-8")
            encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
            page.goto(fixtures.ORIGIN + "/game-engine.html#c=" + encoded)
        page.locator("#startOverlay").wait_for(state="attached")
        return page

    def test_real_export_starts_with_or_without_title_and_can_be_completed(self):
        self.open_editor()
        for mode in ["standalone", "engine"]:
            for enabled in [False, True]:
                with self.subTest(mode=mode, enabled=enabled):
                    page = self.open_game(mode, enabled)
                    if enabled:
                        page.locator("#startOverlay").wait_for(state="visible")
                        page.locator("#startBtn").click()
                    page.locator("#startOverlay").wait_for(state="hidden")
                    if not enabled:
                        # Guard the runtime independently of the editor's
                        # parent-side screen mapping. No live checkbox value
                        # is sent: the compiled false setting must be honored.
                        page.evaluate("""postMessage({kind: 'rope-editor-layout',
                            enabled: true, screen: 'title', pose: 'rope'}, '*')""")
                        page.wait_for_function("document.querySelector('#charGif').dataset.pose === 'rope'")
                        page.locator("#startOverlay").wait_for(state="hidden")
                        page.evaluate("""postMessage({kind: 'rope-editor-layout',
                            enabled: false, screen: 'title'}, '*')""")
                        page.wait_for_function("document.querySelector('#charGif').dataset.pose === 'stand'")
                    self.assertEqual(page.locator("#qtext").inner_text(), fixtures.FIRST_QUESTION)
                    page.get_by_role("button", name="Да ✓", exact=True).click()
                    page.locator("#winOverlay.show").wait_for(state="visible")
                    self.assertIn("✅ 1", page.locator("#winStats").inner_text())
                    page.close()


if __name__ == "__main__":
    unittest.main()
