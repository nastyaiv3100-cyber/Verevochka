"""Browser regressions for question drafts, answer syntax, and media ownership."""

import json
from pathlib import Path
import unittest

import test_genially_export as exports


class QuestionEditorTest(unittest.TestCase):
    setUpClass = classmethod(exports.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(exports.GeniallyExportTest.tearDownClass.__func__)
    setUp = exports.GeniallyExportTest.setUp
    tearDown = exports.GeniallyExportTest.tearDown
    route = exports.GeniallyExportTest.route
    open_editor = exports.GeniallyExportTest.open_editor
    import_settings = exports.GeniallyExportTest.import_settings

    def settings(self):
        return self.editor.evaluate("readSettings()")

    def set_questions(self, questions):
        self.editor.evaluate("""questions => {
            originalConfig.questions = questions;
            restoreQuestionEditorState(null); renderQuestions();
        }""", questions)

    def test_decimal_commas_semicolon_alternatives_and_gaps_round_trip(self):
        self.open_editor()
        questions = [
            {"type": "input", "q": "Половина?", "accepted": ["0,5", "0.5"]},
            {"type": "input", "q": "Фраза?", "accepted": ["red, blue"]},
            {"type": "gaps", "q": "Заполни", "sentence": "I ___ to ___ .", "gaps": [["go", "walk"], "school"]},
            {"type": "multi", "q": "Дроби?", "a": ["0,5", "1,5", "2,5"], "correct": [0, 1]},
        ]
        parsed = self.editor.evaluate(r"""questions => parseQuickQuestions(questions.map(quickLineForQuestion).join('\n'))""", questions)
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["questions"], questions)
        legacy = self.editor.evaluate("parseQuickQuestions('[INPUT] Половина? (0,5)\\n[INPUT] Слово? (кот, кошка)')")
        self.assertEqual(legacy["errors"], [])
        self.assertEqual(legacy["questions"][0]["accepted"], ["0,5"])
        self.assertEqual(legacy["questions"][1]["accepted"], ["кот", "кошка"])

    def test_switching_modes_preserves_card_edits_and_applies_quick_draft(self):
        self.open_editor()
        self.editor.locator("#modeCards").click()
        self.editor.locator(".qText").first.fill("Изменено в карточке")
        self.editor.locator("#modeQuick").click()
        self.assertIn("Изменено в карточке", self.editor.locator("#quickQuestions").input_value())
        self.editor.locator("#quickQuestions").fill("[INPUT] Новый вопрос (0,5; 0.5)")
        self.editor.locator("#modeCards").click()
        self.assertTrue(self.editor.locator("#questionCardsPanel").is_visible())
        self.assertEqual(self.settings()["questions"][0]["accepted"], ["0,5", "0.5"])
        self.editor.locator("#modeQuick").click()
        self.editor.locator("#quickQuestions").fill("[INPUT] Не дописано (")
        self.editor.locator("#modeCards").click()
        self.assertTrue(self.editor.locator("#quickPanel").is_visible())
        self.assertIn("Строка 1", self.editor.locator("#quickStatus").inner_text())
        self.editor.evaluate("renderQuestions()")
        self.assertEqual(self.editor.locator("#quickQuestions").input_value(), "[INPUT] Не дописано (")
        self.editor.locator("#syncQuickQuestions").click()
        self.assertEqual(self.editor.locator("#quickQuestions").input_value(), "[INPUT] Не дописано (")

    def test_clearing_the_quick_block_opens_empty_cards_and_allows_new_questions(self):
        self.open_editor()
        for empty in ["", " \n\t\n"]:
            with self.subTest(text=repr(empty)):
                self.import_settings({"questions": [{
                    "type": "choice", "q": "Вопрос, который удаляют",
                    "a": ["Да", "Нет"], "correct": 0,
                    "image": exports.ORIGIN + "/assets/background.webp",
                }]})
                self.editor.locator("#quickQuestions").fill(empty)
                self.editor.locator("#modeCards").click()
                self.assertTrue(self.editor.locator("#questionCardsPanel").is_visible())
                self.assertEqual(self.settings()["questions"], [])
                self.assertEqual(self.editor.locator("#questionList .question").count(), 0)
                self.editor.wait_for_function("""() =>
                    document.querySelector('#copyGeniallyCode').disabled &&
                    document.querySelector('#downloadGame').disabled
                """)

                self.editor.locator("#addQuestion").click()
                self.editor.locator(".qText").fill("Сколько будет шесть на семь?")
                self.editor.locator(".qType").select_option("input")
                self.editor.locator(".accepted").fill("42")
                image = exports.ORIGIN + "/assets/hero-eat.webp"
                self.editor.locator(".qImageUrl").fill(image)
                self.editor.locator("#modeQuick").click()
                self.assertIn("[INPUT] Сколько будет шесть на семь? (42)",
                              self.editor.locator("#quickQuestions").input_value())
                self.editor.locator("#modeCards").click()
                question = self.settings()["questions"][0]
                self.assertEqual(question["accepted"], ["42"])
                self.assertEqual(question["image"], image)
                self.assertEqual(self.editor.evaluate("validateQuestions(readSettings().questions)"), [])
                frame = self.editor.locator("#preview").element_handle().content_frame()
                frame.locator("#startBtn").wait_for(state="attached")
                frame.locator(".answerInputRow input").wait_for(state="attached")
                self.assertEqual(frame.get_by_role("heading", name="Проверьте задания", exact=True).count(), 0)
                self.editor.locator("#questionList .delete").click()
                self.assertEqual(self.settings()["questions"], [])
                self.assertEqual(self.editor.locator("#questionList .question").count(), 0)
                self.assertTrue(self.editor.locator("#addQuestion").is_visible())

    def test_switching_choice_to_input_preserves_the_answer_image_and_playable_preview(self):
        self.open_editor()
        image = exports.data_url(exports.ROOT / "assets/editor-logo.webp")
        question = {"type": "choice", "q": "Впиши периметр квадрата со стороной 9 см.",
                    "a": ["18", "36", "81"], "correct": 1, "image": image}
        self.import_settings({"questions": [question], "shuffleQuestions": False, "sound": False})
        self.editor.locator("#modeCards").click()
        self.editor.locator(".qType").select_option("input")
        converted = self.settings()["questions"][0]
        self.assertEqual(converted["type"], "input")
        self.assertEqual(converted["q"], question["q"])
        self.assertEqual(converted["image"], image)
        self.assertEqual(converted["accepted"], ["36"])
        self.assertEqual(self.editor.locator(".accepted").input_value(), "36")
        self.assertEqual(self.editor.evaluate("validateQuestions(readSettings().questions)"), [])
        frame = self.editor.locator("#preview").element_handle().content_frame()
        frame.locator(".answerInputRow input").wait_for(state="attached")
        self.assertEqual(frame.get_by_role("heading", name="Проверьте задания", exact=True).count(), 0)

        code = exports.GeniallyExportTest.export_code(self)
        host, game, _ = exports.GeniallyExportTest.load_iframe(self, code)
        game.locator("#startBtn").click()
        exports.GeniallyExportTest.assert_image(self, game, "#questionImage", image)
        game.locator(".answerInputRow input").fill("36")
        game.locator(".checkAnswerBtn").click()
        game.locator("#winOverlay.show").wait_for(state="visible")
        self.assertEqual(game.locator("#hudOk").inner_text(), "1")
        host.close()

    def test_input_answer_survives_a_round_trip_through_choice_format(self):
        self.open_editor()
        self.import_settings({"questions": [{
            "type": "input", "q": "Сколько будет 0,2 + 0,3?", "accepted": ["0,5"],
        }]})
        self.editor.locator("#modeCards").click()
        self.editor.locator(".qType").select_option("choice")
        choice = self.settings()["questions"][0]
        self.assertEqual(choice["a"][choice["correct"]], "0,5")
        self.editor.locator(".qType").select_option("input")
        self.assertEqual(self.editor.locator(".accepted").input_value(), "0,5")
        self.assertEqual(self.settings()["questions"][0]["accepted"], ["0,5"])
        self.assertEqual(self.editor.evaluate("validateQuestions(readSettings().questions)"), [])

    def test_reordered_inserted_and_removed_lines_keep_their_images(self):
        self.open_editor()
        questions = [
            {"type": "open", "q": "Первый", "image": exports.ORIGIN + "/assets/background.webp"},
            {"type": "open", "q": "Второй", "image": exports.ORIGIN + "/assets/rope-vertical.webp"},
            {"type": "open", "q": "Без картинки"},
        ]
        self.set_questions(questions)
        self.editor.locator("#quickQuestions").fill("[OPEN] Новый\n[OPEN] Второй\n[OPEN] Первый")
        self.editor.locator("#applyQuickQuestions").click()
        after = self.settings()["questions"]
        self.assertNotIn("image", after[0])
        self.assertEqual(after[1]["image"], questions[1]["image"])
        self.assertEqual(after[2]["image"], questions[0]["image"])
        self.editor.locator("#quickQuestions").fill("[OPEN] Новый\n[OPEN] Второй")
        self.editor.locator("#applyQuickQuestions").click()
        self.assertEqual(self.settings()["questions"], after)
        self.assertIn("Не удалось однозначно сохранить картинки", self.editor.locator("#quickStatus").inner_text())

    def test_image_ambiguity_blocks_changes_and_unchanged_duplicate_lines_are_safe(self):
        self.open_editor()
        questions = [
            {"type": "open", "q": "Одинаковый", "image": exports.ORIGIN + "/assets/background.webp"},
            {"type": "open", "q": "Одинаковый", "image": exports.ORIGIN + "/assets/rope-vertical.webp"},
        ]
        self.set_questions(questions)
        self.editor.locator("#applyQuickQuestions").click()
        self.assertEqual(self.settings()["questions"], questions)
        self.editor.locator("#quickQuestions").fill("[OPEN] Одинаковый\n[OPEN] Одинаковый\n[OPEN] Новый")
        self.editor.locator("#applyQuickQuestions").click()
        self.assertEqual(self.settings()["questions"], questions)
        self.assertIn("Картинки и вопросы не изменены", self.editor.locator("#quickStatus").inner_text())

    def test_choice_options_after_third_and_multi_selection_are_editable(self):
        self.open_editor()
        self.set_questions([{"type": "choice", "q": "Четыре", "a": ["A", "B", "C", "D"], "correct": 3}])
        self.editor.locator("#modeCards").click()
        self.assertEqual(self.editor.locator(".option").count(), 4)
        self.assertEqual(self.editor.locator(".correct").input_value(), "3")
        self.editor.locator(".option").nth(3).fill("Четвёртый")
        self.editor.locator(".addOption").click()
        self.assertEqual(self.editor.locator(".option").count(), 5)
        self.editor.locator(".correct").select_option("4")
        self.editor.locator(".removeOption").nth(1).click()
        self.assertEqual(self.settings()["questions"][0]["correct"], 3)
        self.editor.locator(".qType").select_option("multi")
        self.assertEqual(self.settings()["questions"][0]["correct"], [0, 1])
        self.editor.locator(".multiCorrect").nth(2).check()
        self.assertEqual(self.settings()["questions"][0]["correct"], [0, 1, 2])
        self.editor.locator(".qType").select_option("choice")
        self.assertEqual(self.settings()["questions"][0]["correct"], 0)

    def test_incomplete_json_and_quick_drafts_survive_state_restore(self):
        self.open_editor()
        self.set_questions([{"type": "gaps", "q": "Пропуск", "sentence": "I ___", "gaps": ["go"]}])
        self.editor.locator("#modeCards").click()
        self.editor.locator(".advancedData").fill('{"sentence": "Незавершено')
        state = self.editor.evaluate("getQuestionEditorState()")
        self.assertEqual(state["drafts"], ['{"sentence": "Незавершено'])
        self.editor.evaluate("state => {restoreQuestionEditorState(null); renderQuestions();restoreQuestionEditorState(state)}", state)
        self.assertEqual(self.editor.locator(".advancedData").input_value(), '{"sentence": "Незавершено')
        self.assertTrue(self.editor.evaluate("getQuestionEditorErrors().length > 0"))
        self.editor.locator(".advancedData").fill('{"sentence":"I ___","gaps":[{}]}')
        self.assertEqual(self.settings()["questions"][0]["gaps"], ["go"])
        self.assertEqual(self.editor.evaluate("getQuestionEditorState().drafts"), ['{"sentence":"I ___","gaps":[{}]}'])
        self.assertTrue(self.editor.evaluate("getQuestionEditorErrors().length > 0"))
        self.editor.locator(".advancedData").fill('{"sentence":"I ___","gaps":[["go","walk"]]}')
        self.assertEqual(self.editor.evaluate("getQuestionEditorErrors()"), [])
        self.editor.locator("#modeQuick").click()
        self.assertIn("go; walk", self.editor.locator("#quickQuestions").input_value())

    def test_export_blocks_missing_answer_then_grades_decimal_correctly(self):
        self.open_editor()
        self.import_settings({"questions": [{
            "type": "input", "q": "Сколько будет 0,2 + 0,3?", "accepted": [""],
        }], "shuffleQuestions": False, "sound": False})
        self.editor.locator('[data-editor-tab="export"]').click()
        self.editor.wait_for_function("""() =>
            document.querySelector('#downloadGame').disabled &&
            document.querySelector('#copyGeniallyCode').disabled &&
            !document.querySelector('#geniallyWarning').hidden
        """)
        self.assertEqual(self.editor.locator("#geniallyEmbedCode").input_value(), "")
        self.assertIn("допустимый ответ", self.editor.locator("#geniallyWarningText").inner_text())
        self.assertTrue(self.editor.locator("#openHtmlPreview").is_disabled())
        # A draft must remain downloadable even while publishing is blocked.
        with self.editor.expect_download() as pending:
            self.editor.locator("#saveConfig").click()
        draft = json.loads(Path(pending.value.path()).read_text())
        self.assertEqual(draft["questions"][0]["accepted"], [""])
        self.editor.locator('[data-editor-tab="editor"]').click()
        self.editor.locator("#modeCards").click()
        self.editor.locator(".accepted").fill("0,5")
        self.editor.locator("#modeQuick").click()
        self.editor.locator("#applyQuickQuestions").click()
        self.assertEqual(self.settings()["questions"][0]["accepted"], ["0,5"])
        code = exports.GeniallyExportTest.export_code(self)
        host, game, _ = exports.GeniallyExportTest.load_iframe(self, code)
        game.locator("#startBtn").click()
        game.locator(".answerInputRow input").fill("0")
        game.locator(".checkAnswerBtn").click()
        game.wait_for_function("document.querySelector('#winOverlay').classList.contains('show') || STATE.no === 1")
        self.assertEqual(game.locator("#hudOk").inner_text(), "0")
        game.locator(".answerInputRow input").fill("0,5")
        game.locator(".checkAnswerBtn").click()
        game.locator("#winOverlay.show").wait_for(state="visible")
        self.assertEqual(game.locator("#hudOk").inner_text(), "1")
        host.close()

    def test_validator_handles_bad_structures_and_incomplete_cards(self):
        self.open_editor()
        invalid = [None, {}, {"type": "choice", "q": "", "a": ["A", ""], "correct": 9},
                   {"type": "input", "q": "Ответ", "accepted": []},
                   {"type": "multi", "q": "Выбор", "a": ["A", "B"], "correct": [3]},
                   {"type": "matching", "q": "Пары", "pairs": [None]},
                   {"type": "categories", "q": "Категории", "categories": [None]},
                   {"type": "gaps", "q": "Пропуски", "sentence": "___ ___", "gaps": ["A"]}]
        errors = self.editor.evaluate("questions => validateQuestions(questions)", invalid)
        self.assertGreaterEqual(len(errors), len(invalid))
        self.set_questions(invalid)
        self.assertEqual(self.editor.locator(".question").count(), len(invalid))
        self.editor.locator("#modeCards").click()
        self.editor.locator(".correct").first.select_option("0")

    def test_valid_json_with_bad_parameter_shapes_stays_in_drafts(self):
        self.open_editor()
        questions = [
            {"type": "matching", "q": "Пары", "pairs": [{"left": "A", "right": "1"}, {"left": "B", "right": "2"}]},
            {"type": "order", "q": "Порядок", "items": ["A", "B"]},
        ]
        self.set_questions(questions)
        self.editor.locator("#modeCards").click()
        bad_drafts = ['{"pairs":[1]}', '{"items":[{}]}']
        for i, draft in enumerate(bad_drafts):
            self.editor.locator(".advancedData").nth(i).fill(draft)
        self.assertEqual(self.settings()["questions"], questions)
        state = self.editor.evaluate("getQuestionEditorState()")
        self.assertEqual(state["drafts"], bad_drafts)
        self.editor.evaluate("state => restoreQuestionEditorState(state)", state)
        for i, draft in enumerate(bad_drafts):
            self.assertEqual(self.editor.locator(".advancedData").nth(i).input_value(), draft)
        self.assertEqual(self.settings()["questions"], questions)
        self.assertTrue(self.editor.evaluate("getQuestionEditorErrors().length > 0"))

    def test_error_word_validation_matches_runtime_unicode_punctuation(self):
        self.open_editor()
        for token in ["“go”", "—go—", "«go»", "‘go’", "(go)", "GO!"]:
            for word in ["go", token]:
                with self.subTest(token=token, word=word):
                    errors = self.editor.evaluate("q => validateQuestions([q])", {
                        "type": "error", "q": "Ошибка?", "sentence": "She " + token + " to school.", "errorWord": word,
                    })
                    self.assertEqual(errors, [])
        errors = self.editor.evaluate("q => validateQuestions([q])", {
            "type": "error", "q": "Ошибка?", "sentence": "She goes to school.", "errorWord": "—go—",
        })
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
