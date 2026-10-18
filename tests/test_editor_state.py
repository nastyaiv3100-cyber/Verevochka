"""Browser regressions for project recovery, history, imports and manual export.

Run with ``python -m unittest discover -s tests -v``.  Like the existing export
checks, these serve the real editor from an offline, synthetic HTTPS origin.
"""

import copy
import json
from pathlib import Path
import re
import unittest

import test_genially_export as export_tests


class EditorStateTest(unittest.TestCase):
    # Reuse the browser/HTTPS fixture without inheriting and rerunning its tests.
    setUpClass = classmethod(export_tests.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(export_tests.GeniallyExportTest.tearDownClass.__func__)
    setUp = export_tests.GeniallyExportTest.setUp
    tearDown = export_tests.GeniallyExportTest.tearDown
    route = export_tests.GeniallyExportTest.route
    open_editor = export_tests.GeniallyExportTest.open_editor
    import_settings = export_tests.GeniallyExportTest.import_settings
    export_code = export_tests.GeniallyExportTest.export_code

    def settings(self):
        return self.editor.evaluate("readSettings()")

    def question_editor(self):
        return self.editor.evaluate("getQuestionEditorState()")

    def wait_saved(self, marker):
        self.editor.wait_for_function("""marker => {
            const status = document.querySelector('#saveStatus');
            return status && Object.keys(localStorage).some(key =>
                (localStorage.getItem(key) || '').includes(marker));
        }""", arg=marker)
        self.assertTrue(self.editor.locator("#saveStatus").is_visible())
        self.assertEqual(self.editor.locator("#saveStatus").get_attribute("role"), "status")

    def reload_editor(self):
        self.editor.reload()
        self.editor.wait_for_function("typeof getQuestionEditorState === 'function'")

    def downloaded_settings(self):
        with self.editor.expect_download() as pending:
            self.editor.locator("#saveConfig").click()
        download = pending.value
        self.assertEqual(download.failure(), None)
        return json.loads(Path(download.path()).read_text(encoding="utf-8"))

    def test_reload_restores_settings_uploaded_images_and_unapplied_quick_draft(self):
        self.open_editor()
        image = export_tests.ROOT / "assets/editor-logo.webp"
        self.editor.locator("#titleImageFile").set_input_files(image)
        self.editor.wait_for_function("readSettings().theme.titleImageData.startsWith('data:image/')")
        self.editor.locator("#startTitle").fill("Сохранённый заголовок 🐈")
        # An unfinished draft must survive even though it cannot yet be applied.
        draft = "[INPUT] pending-quick-draft: дробь 0,5 (0,5"
        self.editor.locator("#quickQuestions").fill(draft)
        self.wait_saved("pending-quick-draft")
        expected_settings = self.settings()
        expected_editor = self.question_editor()
        backup = self.downloaded_settings()
        self.assertEqual(backup.pop("_editor", None), expected_editor,
                         "Manual backups must retain an unapplied question draft")
        self.assertEqual(backup, expected_settings)

        self.reload_editor()
        self.assertEqual(self.settings(), expected_settings)
        self.assertEqual(self.question_editor(), expected_editor)
        self.assertEqual(self.editor.locator("#quickQuestions").input_value(), draft)
        self.assertTrue(self.editor.locator("#quickPanel").is_visible())
        self.assertEqual(self.editor.locator("#titleImagePreview").get_attribute("src"),
                         export_tests.data_url(image))

    def test_reload_restores_invalid_advanced_draft_and_cards_mode(self):
        self.open_editor()
        self.import_settings({"questions": [{
            "type": "order", "q": "Собери предложение", "items": ["Кот", "спит"],
            "image": export_tests.data_url(export_tests.ROOT / "assets/food.webp"),
        }]})
        self.editor.locator("#modeCards").click()
        draft = '{"items": ["kept-advanced-draft",'
        self.editor.locator(".advancedData").fill(draft)
        self.wait_saved("kept-advanced-draft")
        expected_settings = self.settings()
        expected_editor = self.question_editor()
        backup = self.downloaded_settings()
        self.assertEqual(backup.pop("_editor", None), expected_editor,
                         "Manual backups must retain unfinished advanced JSON")
        self.assertEqual(backup, expected_settings)

        self.reload_editor()
        self.assertEqual(self.settings(), expected_settings)
        self.assertEqual(self.question_editor(), expected_editor)
        self.assertTrue(self.editor.locator("#questionCardsPanel").is_visible())
        self.assertEqual(self.editor.locator(".advancedData").input_value(), draft)

    def test_partial_import_preserves_omitted_settings_and_nested_media(self):
        self.open_editor()
        image = export_tests.data_url(export_tests.ROOT / "assets/editor-logo.webp")
        self.import_settings({
            "startTitle": "До импорта", "revealCorrect": True, "sound": False,
            "theme": {"titleBg": "#123456", "titleImageData": image},
            "feedbackImages": {"win": image, "lose": image},
        })
        expected = copy.deepcopy(self.settings())
        expected["startTitle"] = "После частичного импорта"
        expected["theme"]["titleBg"] = "#654321"
        expected["feedbackImages"]["win"] = ""

        self.import_settings({
            "startTitle": expected["startTitle"],
            "theme": {"titleBg": "#654321"}, "feedbackImages": {"win": ""},
        })
        self.assertEqual(self.settings(), expected)
        self.assertTrue(self.editor.locator("#revealCorrect").is_checked())

    def test_import_replaces_explicit_asset_maps_and_updates_visible_controls(self):
        self.open_editor()
        pristine = self.settings()
        self.import_settings({
            "assetFiles": {"catStand": export_tests.data_url(export_tests.ROOT / "assets/food.webp")},
            "assetOverrides": {"food": export_tests.ORIGIN + "/assets/editor-logo.webp"},
            "ropeLength": 0.3,
        })
        self.assertEqual(self.editor.locator("#asset-food").input_value(),
                         export_tests.ORIGIN + "/assets/editor-logo.webp")
        self.assertEqual(self.editor.locator("#ropeLength").locator("..").locator("output").text_content(), "30%")
        self.import_settings(pristine)
        self.assertEqual(self.settings(), pristine,
                         "An explicit empty asset map must clear the previous project's images")
        self.assertEqual(self.editor.locator("#asset-food").input_value(),
                         export_tests.ORIGIN + "/assets/food.webp")
        expected_percent = str(round(pristine["ropeLength"] * 100)) + "%"
        self.assertEqual(self.editor.locator("#ropeLength").locator("..").locator("output").text_content(), expected_percent)

    def test_compression_is_autosaved_and_participates_in_general_undo(self):
        self.open_editor()
        self.import_settings({"assetFiles": {
            "background": export_tests.data_url(export_tests.ROOT / "assets/background.webp"),
        }})
        before = self.settings()
        self.editor.locator("#lightenCode").click()
        self.editor.wait_for_function("""() =>
            !document.querySelector('#lightenCode').disabled &&
            !document.querySelector('#undoEdit').disabled
        """)
        after = self.settings()
        self.assertNotEqual(after["assetFiles"]["background"], before["assetFiles"]["background"])
        self.editor.locator("#undoEdit").click()
        self.assertEqual(self.settings(), before)
        self.editor.locator("#redoEdit").click()
        self.assertEqual(self.settings(), after)
        self.reload_editor()
        self.assertEqual(self.settings(), after)

    def test_invalid_structural_import_is_atomic_and_reports_the_problem(self):
        self.open_editor()
        draft = "[INPUT] keep-import-draft ("
        self.editor.locator("#quickQuestions").fill(draft)
        expected_settings = self.settings()
        expected_editor = self.question_editor()
        for invalid in [
            {"startTitle": "MUST NOT APPLY", "questions": "broken"},
            {"startTitle": "MUST NOT APPLY", "questions": [None]},
            {"startTitle": "MUST NOT APPLY", "theme": []},
        ]:
            with self.subTest(invalid=invalid):
                self.import_settings(invalid)
                self.assertEqual(self.settings(), expected_settings)
                self.assertEqual(self.question_editor(), expected_editor)
                message = self.editor.locator("#toast").inner_text()
                self.assertRegex(message, re.compile(r"(не удалось|ошиб|некоррект)", re.I))
                self.assertRegex(message, re.compile(r"(JSON|настрой|вопрос|формат)", re.I))
                self.assertTrue(self.editor.locator("#toast.show").is_visible())

    def test_confirmed_reset_removes_saved_project_and_survives_another_reload(self):
        self.editor.goto(export_tests.ORIGIN + "/index.html")
        self.editor.wait_for_function("typeof readSettings === 'function'")
        defaults = self.settings()
        self.editor.locator("#startTitle").fill("reset-saved-project")
        self.editor.locator("#quickQuestions").fill("[OPEN] Черновик для удаления")
        self.wait_saved("reset-saved-project")

        self.editor.locator("#resetAll").click()
        self.editor.locator("#cancelReset").click()
        self.assertEqual(self.settings()["startTitle"], "reset-saved-project")
        self.editor.locator("#resetAll").click()
        with self.editor.expect_navigation():
            self.editor.locator("#confirmReset").click()
        self.editor.wait_for_function("typeof readSettings === 'function'")
        self.assertEqual(self.settings(), defaults)
        self.assertNotIn("Черновик для удаления", self.editor.locator("#quickQuestions").input_value())
        self.reload_editor()
        self.assertEqual(self.settings(), defaults)

    def assert_save_failure_and_download(self, title):
        self.editor.locator("#startTitle").fill(title)
        self.editor.wait_for_function("""() => {
            const status=document.querySelector('#saveStatus');
            return status && /не удалось|ошиб|недоступ|не сохран/i.test(status.textContent);
        }""")
        self.assertTrue(self.editor.locator("#saveStatus").is_visible())
        message = self.editor.locator("#saveStatus").inner_text()
        self.assertRegex(message, re.compile(r"(JSON|скача|файл)", re.I),
                         "Save failures must explain how to keep a manual backup")
        settings = self.settings()
        backup = self.downloaded_settings()
        editor_metadata = backup.pop("_editor", None)
        if editor_metadata is not None:
            self.assertEqual(editor_metadata, self.question_editor())
        self.assertEqual(backup, settings)
        self.assertEqual(settings["startTitle"], title)

    def test_storage_quota_failure_is_visible_and_json_save_still_works(self):
        self.open_editor()
        self.editor.evaluate("""() => {
            Storage.prototype.setItem = () => {
                throw new DOMException('Synthetic storage quota exhausted', 'QuotaExceededError');
            };
        }""")
        self.assert_save_failure_and_download("quota-failure-project")

    def test_storage_security_denial_is_visible_and_does_not_prevent_editing(self):
        self.context.add_init_script("""Object.defineProperty(window, 'localStorage', {
            configurable: true,
            get() { throw new DOMException('Synthetic storage denied', 'SecurityError'); }
        });""")
        self.open_editor()
        self.assert_save_failure_and_download("denied-storage-project")

    def test_undo_and_redo_restore_question_text_answers_images_and_settings(self):
        self.open_editor()
        self.editor.locator("#modeCards").click()
        original = self.settings()
        self.editor.locator(".qText").first.fill("Отредактированный вопрос 🐈")
        self.editor.locator(".option").first.fill("Новый правильный ответ")
        image = export_tests.ROOT / "assets/editor-logo.webp"
        self.editor.locator(".qImageFile").first.set_input_files(image)
        self.editor.wait_for_function("readSettings().questions[0].image?.startsWith('data:image/')")
        self.editor.locator("#startTitle").fill("history-final-project")
        self.wait_saved("history-final-project")
        final = self.settings()
        self.assertNotEqual(final, original)

        for _ in range(20):
            if self.settings() == original:
                break
            self.assertTrue(self.editor.locator("#undoEdit").is_enabled())
            self.editor.locator("#undoEdit").click()
        self.assertEqual(self.settings(), original)
        for _ in range(20):
            if self.settings() == final:
                break
            self.assertTrue(self.editor.locator("#redoEdit").is_enabled())
            self.editor.locator("#redoEdit").click()
        self.assertEqual(self.settings(), final)
        self.assertEqual(final["questions"][0]["image"], export_tests.data_url(image))

    def test_keyboard_history_shortcuts_and_native_text_undo(self):
        self.open_editor()
        original_title = self.settings()["startTitle"]
        self.editor.locator("#startTitle").fill("keyboard-final-project")
        self.wait_saved("keyboard-final-project")
        self.editor.locator("#undoEdit").focus()
        self.editor.keyboard.press("Control+z")
        self.editor.wait_for_function("title => readSettings().startTitle === title", arg=original_title)
        self.editor.keyboard.press("Control+Shift+z")
        self.editor.wait_for_function("readSettings().startTitle === 'keyboard-final-project'")
        self.editor.keyboard.press("Meta+z")
        self.editor.wait_for_function("title => readSettings().startTitle === title", arg=original_title)
        self.editor.keyboard.press("Control+y")
        self.editor.wait_for_function("readSettings().startTitle === 'keyboard-final-project'")

        field = self.editor.locator("#startTitle")
        field.focus()
        field.press("End")
        self.editor.keyboard.type("!")
        self.editor.evaluate("""() => {
            window.__nativeUndoPrevented = null;
            document.addEventListener('keydown', event => {
                if(event.key.toLowerCase()==='z' && (event.ctrlKey || event.metaKey))
                    window.__nativeUndoPrevented = event.defaultPrevented;
            });
        }""")
        self.editor.keyboard.press("Control+z")
        self.assertFalse(self.editor.evaluate("window.__nativeUndoPrevented"))
        self.assertEqual(field.input_value(), "keyboard-final-project")

    def configure_clipboard(self, native_ok, fallback_ok):
        self.editor.evaluate("""({nativeOk, fallbackOk}) => {
            window.__clipboardWrites = [];
            window.__copyFallbackCalls = [];
            Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{
                async writeText(text) {
                    window.__clipboardWrites.push(text);
                    if(!nativeOk) throw new DOMException('Synthetic clipboard denial', 'NotAllowedError');
                }
            }});
            document.execCommand = command => {
                window.__copyFallbackCalls.push(command);
                return fallbackOk;
            };
        }""", {"nativeOk": native_ok, "fallbackOk": fallback_ok})

    def test_genially_code_is_visible_readonly_and_can_be_selected_manually(self):
        self.open_editor()
        code = self.export_code()
        area = self.editor.locator("#geniallyEmbedCode")
        self.assertTrue(area.is_visible())
        self.assertNotEqual(area.get_attribute("aria-hidden"), "true")
        self.assertTrue(area.evaluate("area => area.readOnly"))
        self.assertGreaterEqual(area.evaluate("area => area.tabIndex"), 0)
        area.click()
        area.press("Control+a")
        self.assertEqual(area.evaluate("area => area.value.slice(area.selectionStart, area.selectionEnd)"), code)

    def test_copy_reports_success_when_native_clipboard_really_succeeds(self):
        self.open_editor()
        code = self.export_code()
        self.configure_clipboard(native_ok=True, fallback_ok=False)
        self.editor.locator("#copyGeniallyCode").click()
        self.editor.wait_for_function("document.querySelector('#toast').textContent.includes('скопирован')")
        self.assertEqual(self.editor.evaluate("window.__clipboardWrites"), [code])
        self.assertEqual(self.editor.evaluate("window.__copyFallbackCalls"), [])

    def test_copy_reports_success_only_if_legacy_fallback_returns_true(self):
        self.open_editor()
        code = self.export_code()
        self.configure_clipboard(native_ok=False, fallback_ok=True)
        self.editor.locator("#copyGeniallyCode").click()
        self.editor.wait_for_function("document.querySelector('#toast').textContent.includes('скопирован')")
        self.assertEqual(self.editor.evaluate("window.__clipboardWrites"), [code])
        self.assertEqual(self.editor.evaluate("window.__copyFallbackCalls"), ["copy"])

    def test_failed_copy_instructs_manual_copy_and_keeps_code_accessible(self):
        self.open_editor()
        code = self.export_code()
        self.configure_clipboard(native_ok=False, fallback_ok=False)
        self.editor.locator("#copyGeniallyCode").click()
        self.editor.wait_for_function("/Ctrl|⌘|Command/i.test(document.querySelector('#toast').textContent)")
        message = self.editor.locator("#toast").inner_text()
        self.assertNotIn("скопирован", message.lower())
        self.assertRegex(message, re.compile(r"(Ctrl|⌘|Command).*[CС]", re.I))
        self.assertTrue(self.editor.locator("#geniallyEmbedCode").is_visible())
        self.assertEqual(self.editor.locator("#geniallyEmbedCode").input_value(), code)
        self.assertEqual(self.editor.evaluate("window.__copyFallbackCalls"), ["copy"])


if __name__ == "__main__":
    unittest.main()
