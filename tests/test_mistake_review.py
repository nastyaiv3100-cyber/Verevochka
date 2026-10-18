"""Real gameplay checks for the final mistake review and focused practice.

The tests exercise exported standalone HTML and the Genially game engine using
actual answer controls. They reuse the HTTPS router without inheriting tests.
"""

import unittest

import test_genially_export as export_helpers
import test_gameplay_mobile as mobile_helpers


class MistakeReviewTest(unittest.TestCase):
    GAME_FORMATS = ("standalone", "engine")

    setUpClass = classmethod(export_helpers.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(export_helpers.GeniallyExportTest.tearDownClass.__func__)
    setUp = export_helpers.GeniallyExportTest.setUp
    tearDown = export_helpers.GeniallyExportTest.tearDown
    route = export_helpers.GeniallyExportTest.route
    open_editor = export_helpers.GeniallyExportTest.open_editor
    import_settings = export_helpers.GeniallyExportTest.import_settings
    open_game = mobile_helpers.GameplayMobileTest.open_game
    assert_reachable = mobile_helpers.GameplayMobileTest.assert_reachable

    def start(self, mode, questions, **settings):
        page = self.open_game(mode, {
            "questions": questions, "shuffleQuestions": False, "sound": False,
            **settings,
        })
        page.locator("#startBtn").click()
        return page

    def answer_choice(self, page, text):
        page.locator("#answers").get_by_role("button", name=text, exact=True).click()

    def show_review(self, page, overlay):
        page.locator(overlay + ".show").wait_for(state="visible")
        review = page.locator(overlay + " details.mistakeReview")
        self.assertTrue(review.is_visible())
        if not review.evaluate("element => element.open"):
            review.locator("summary").click()
        return review

    def review_text(self, review, selector):
        return "\n".join(review.locator(selector).all_text_contents())

    def assert_review_question(self, review, expected):
        headings = review.locator(".mistakeQuestion").all_text_contents()
        self.assertEqual(len(headings), 1)
        self.assertTrue(headings[0].endswith(expected), headings[0])

    def test_corrected_mistakes_are_deduplicated_and_retry_restores_full_replay(self):
        self.open_editor()
        questions = [
            {"type": "choice", "q": "Вопрос с ошибками", "a": ["Верно", "Ошибка А", "Ошибка Б"], "correct": 0},
            {"type": "choice", "q": "Вопрос без ошибок", "a": ["Чисто", "Неверно"], "correct": 0},
        ]
        for mode in self.GAME_FORMATS:
            with self.subTest(mode=mode):
                page = self.start(mode, questions)
                self.answer_choice(page, "Ошибка А")
                self.answer_choice(page, "Ошибка Б")
                self.answer_choice(page, "Верно")
                page.locator("#qtext").filter(has_text=questions[1]["q"]).wait_for()
                self.answer_choice(page, "Чисто")
                review = self.show_review(page, "#winOverlay")
                self.assert_review_question(review, questions[0]["q"])
                wrong = self.review_text(review, ".mistakeStudentAnswer")
                self.assertIn("Ошибка А", wrong)
                self.assertIn("Ошибка Б", wrong)
                self.assertIn("Верно", self.review_text(review, ".mistakeCorrectAnswer"))
                self.assertNotIn(questions[1]["q"], review.inner_text())
                page.locator("#retryWinMistakesBtn").click()
                self.assertTrue(page.locator("#startOverlay").is_hidden(), "Focused practice skips the title page")
                self.assertEqual(page.locator("#hudTotal").inner_text(), "1")
                self.assertEqual(page.locator("#hudOk").inner_text(), "0")
                self.assertEqual(page.locator("#hudHearts").inner_text().count("⚫"), 0)
                self.assertEqual(page.locator("#qtext").inner_text(), questions[0]["q"])
                self.answer_choice(page, "Верно")
                page.locator("#winOverlay.show").wait_for(state="visible")
                self.assertTrue(page.locator("#retryWinMistakesBtn").is_hidden())
                self.assertEqual(page.locator("#winOverlay .mistakeQuestion").count(), 0,
                                 "A clean practice run must not inherit old mistakes")
                page.locator("#playAgainBtn").click()
                self.assertEqual(page.locator("#hudTotal").inner_text(), "2")
                self.assertEqual(page.locator("#qtext").inner_text(), questions[0]["q"])
                self.answer_choice(page, "Верно")
                page.locator("#qtext").filter(has_text=questions[1]["q"]).wait_for()
                self.answer_choice(page, "Чисто")
                page.locator("#winOverlay.show").wait_for(state="visible")
                self.assertIn("✅ 2", page.locator("#winStats").inner_text())
                self.assertTrue(page.locator("#retryWinMistakesBtn").is_hidden())
                page.close()

    def test_identical_prompts_keep_distinct_question_identity(self):
        self.open_editor()
        questions = [
            {"type": "choice", "q": "Одинаковый вопрос", "a": ["Первый ответ", "Первая ошибка"], "correct": 0},
            {"type": "choice", "q": "Одинаковый вопрос", "a": ["Второй ответ", "Вторая ошибка"], "correct": 0},
        ]
        for mode in self.GAME_FORMATS:
            with self.subTest(mode=mode):
                page = self.start(mode, questions)
                for good, bad in [("Первый ответ", "Первая ошибка"), ("Второй ответ", "Вторая ошибка")]:
                    self.answer_choice(page, bad)
                    self.answer_choice(page, good)
                review = self.show_review(page, "#winOverlay")
                self.assertEqual(review.locator(".mistakeQuestion").count(), 2)
                answers = self.review_text(review, ".mistakeCorrectAnswer")
                self.assertIn("Первый ответ", answers)
                self.assertIn("Второй ответ", answers)
                page.locator("#retryWinMistakesBtn").click()
                self.assertEqual(page.locator("#hudTotal").inner_text(), "2")
                self.answer_choice(page, "Первый ответ")
                self.answer_choice(page, "Второй ответ")
                page.locator("#winOverlay.show").wait_for(state="visible")
                self.assertTrue(page.locator("#retryWinMistakesBtn").is_hidden())
                page.close()

    def test_loss_review_excludes_unasked_questions_and_retry_has_fresh_lives(self):
        self.open_editor()
        questions = [
            {"type": "input", "q": "Половина единицы", "accepted": ["0,5", "0.5"]},
            {"type": "choice", "q": "Ещё не заданный вопрос", "a": ["Да", "Нет"], "correct": 0},
        ]
        for mode in self.GAME_FORMATS:
            with self.subTest(mode=mode):
                page = self.start(mode, questions)
                answer = page.locator("#answers input")
                for text in ["0", "0,2", "0,9"]:
                    answer.fill(text)
                    page.locator("#answers .checkAnswerBtn").click()
                review = self.show_review(page, "#overOverlay")
                self.assert_review_question(review, questions[0]["q"])
                self.assertNotIn(questions[1]["q"], review.inner_text())
                wrong = self.review_text(review, ".mistakeStudentAnswer")
                self.assertIn("0,2", wrong)
                self.assertIn("0,9", wrong)
                self.assertIn("0,5", self.review_text(review, ".mistakeCorrectAnswer"))
                page.locator("#retryLoseMistakesBtn").click()
                self.assertEqual(page.locator("#hudTotal").inner_text(), "1")
                self.assertEqual(page.locator("#hudOk").inner_text(), "0")
                self.assertEqual(page.locator("#hudHearts").inner_text().count("⚫"), 0)
                answer.fill("0,5")
                page.locator("#answers .checkAnswerBtn").click()
                page.locator("#winOverlay.show").wait_for(state="visible")
                self.assertIn("✅ 1", page.locator("#winStats").inner_text())
                self.assertTrue(page.locator("#retryWinMistakesBtn").is_hidden())
                page.close()

    def test_review_captures_each_graded_answer_format(self):
        self.open_editor()
        cases = [
            ({"type": "choice", "q": "Выбери", "a": ["Верный выбор", "Плохой выбор"], "correct": 0},
             ["Плохой выбор"], ["Верный выбор"]),
            ({"type": "input", "q": "Впиши", "accepted": ["0,5", "0.5"]}, ["9"], ["0,5"]),
            ({"type": "matching", "q": "Сопоставь", "pairs": [{"left": "Альфа", "right": "один"}, {"left": "Бета", "right": "два"}]},
             ["Альфа", "два"], ["Альфа", "один", "Бета", "два"]),
            ({"type": "order", "q": "Упорядочи", "items": ["первый", "второй"]},
             ["второй", "первый"], ["первый", "второй"]),
            ({"type": "multi", "q": "Выбери несколько", "a": ["Красный", "Синий", "Лишний"], "correct": [0, 1]},
             ["Лишний"], ["Красный", "Синий"]),
            ({"type": "categories", "q": "Распредели", "categories": [{"name": "Животные", "items": ["кот"]}, {"name": "Растения", "items": ["дуб"]}]},
             ["кот", "Растения"], ["кот", "Животные", "дуб", "Растения"]),
            ({"type": "error", "q": "Найди ошибку", "sentence": "Мама мыла раму.", "errorWord": "мыла"},
             ["Мама"], ["мыла"]),
            ({"type": "gaps", "q": "Заполни", "sentence": "___ и ___", "gaps": [["one", "1"], ["two", "2"]]},
             ["bad", "no"], ["one", "two"]),
        ]
        for mode in self.GAME_FORMATS:
            for question, wrong_parts, correct_parts in cases:
                with self.subTest(mode=mode, type=question["type"]):
                    page = self.start(mode, [question])
                    self.submit_format_answer(page, question["type"], wrong=True)
                    self.submit_format_answer(page, question["type"], wrong=False)
                    review = self.show_review(page, "#winOverlay")
                    self.assert_review_question(review, question["q"])
                    wrong_text = self.review_text(review, ".mistakeStudentAnswer")
                    correct_text = self.review_text(review, ".mistakeCorrectAnswer")
                    for text in wrong_parts:
                        self.assertIn(text, wrong_text)
                    for text in correct_parts:
                        self.assertIn(text, correct_text)
                    page.close()

    def submit_format_answer(self, page, kind, wrong):
        answers = page.locator("#answers")
        if kind == "choice":
            self.answer_choice(page, "Плохой выбор" if wrong else "Верный выбор")
        elif kind == "input":
            answers.locator("input").fill("9" if wrong else "0,5")
            answers.locator(".checkAnswerBtn").click()
        elif kind == "matching":
            left = answers.locator(".matchColumn").nth(0)
            right = answers.locator(".matchColumn").nth(1)
            if wrong:
                left.get_by_role("button", name="Альфа", exact=True).click()
                right.get_by_role("button", name="два", exact=True).click()
                answers.locator(".pair-wrong-flash").first.wait_for(state="hidden")
            else:
                for a, b in [("Альфа", "один"), ("Бета", "два")]:
                    left.get_by_role("button", name=a, exact=True).click()
                    right.get_by_role("button", name=b, exact=True).click()
        elif kind == "order":
            while answers.locator(".orderSelected .orderToken").count():
                answers.locator(".orderSelected .orderToken").first.click()
            for word in (["второй", "первый"] if wrong else ["первый", "второй"]):
                answers.locator(".orderChoices").get_by_role("button", name=word, exact=True).click()
            answers.locator(".checkAnswerBtn").click()
        elif kind == "multi":
            for button in answers.locator(".multiOption.selected").all():
                button.click()
            for word in (["Лишний"] if wrong else ["Красный", "Синий"]):
                answers.get_by_role("button", name=word, exact=True).click()
            answers.locator(".checkAnswerBtn").click()
        elif kind == "categories":
            answers.get_by_label("Категория для кот", exact=True).select_option(label="Растения" if wrong else "Животные")
            answers.get_by_label("Категория для дуб", exact=True).select_option(label="Животные" if wrong else "Растения")
            answers.locator(".checkAnswerBtn").click()
        elif kind == "error":
            answers.get_by_role("button", name="Мама" if wrong else "мыла", exact=True).click()
        elif kind == "gaps":
            for index, text in enumerate(["bad", "no"] if wrong else ["one", "two"]):
                answers.locator("input").nth(index).fill(text)
            answers.locator(".checkAnswerBtn").click()
        else:
            self.fail("Unknown fixture type " + kind)

    def test_mobile_review_keeps_untrusted_text_literal_and_actions_reachable(self):
        self.open_editor()
        prompt = '<img src=x onerror="window.reviewInjected=true"> Вопрос ' + "длинное слово " * 25
        wrong = '<svg onload="window.reviewInjected=true">ошибка</svg>'
        correct = '</script><script>window.reviewInjected=true</script> правильный ответ'
        for mode in self.GAME_FORMATS:
            with self.subTest(mode=mode):
                page = self.start(mode, [{"type": "input", "q": prompt, "accepted": [correct]}])
                page.set_viewport_size({"width": 390, "height": 844})
                answer = page.locator("#answers input")
                for value in [wrong, correct]:
                    answer.fill(value)
                    page.locator("#answers .checkAnswerBtn").click()
                review = self.show_review(page, "#winOverlay")
                self.assert_review_question(review, prompt)
                self.assertIn(wrong, self.review_text(review, ".mistakeStudentAnswer"))
                self.assertIn(correct, self.review_text(review, ".mistakeCorrectAnswer"))
                self.assertEqual(review.locator("img, svg, script").count(), 0)
                self.assertFalse(page.evaluate("Boolean(window.reviewInjected)"))
                self.assert_reachable(page, "#retryWinMistakesBtn")
                self.assert_reachable(page, "#playAgainBtn")
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
                page.locator("#retryWinMistakesBtn").click()
                answer.fill(wrong)
                for _ in range(3):
                    page.locator("#answers .checkAnswerBtn").click()
                self.show_review(page, "#overOverlay")
                self.assert_reachable(page, "#retryLoseMistakesBtn")
                self.assert_reachable(page, "#restartBtn")
                self.assert_reachable(page, "#goBackBtn")
                page.close()

    def test_localized_review_preserves_embedded_question_image(self):
        self.open_editor()
        image = export_helpers.data_url(export_helpers.ROOT / "assets/editor-logo.webp")
        question = {"type": "choice", "q": "Авторский вопрос 中文", "a": ["Верный ✓", "Неверный X"], "correct": 0, "image": image}
        for language, title, retry, practice, correct_label in [
            ("en", "Mistake review", "Retry mistakes", "Mistake practice", "Correct answer"),
            ("zh", "错题回顾", "重做错题", "错题练习", "正确答案"),
        ]:
            for mode in self.GAME_FORMATS:
                with self.subTest(mode=mode, language=language):
                    page = self.start(mode, [question], translateInterface=True, uiLanguage=language,
                                      theme={"winBg": "#ffffff", "winBodyColor": "#123456", "cardLabelColor": "#234567"})
                    self.answer_choice(page, "Неверный X")
                    self.answer_choice(page, "Верный ✓")
                    review = self.show_review(page, "#winOverlay")
                    self.assertIn(title, review.locator("summary").inner_text())
                    self.assertEqual(page.locator("#retryWinMistakesBtn").inner_text(), retry)
                    self.assertIn(correct_label, self.review_text(review, ".mistakeCorrectAnswer"))
                    self.assert_review_question(review, question["q"])
                    for selector in ["summary", ".mistakeQuestion", ".mistakeStudentAnswer"]:
                        self.assertEqual(review.locator(selector).first.evaluate("element => getComputedStyle(element).color"),
                                         "rgb(18, 52, 86)")
                    export_helpers.GeniallyExportTest.assert_image(self, page, "#winOverlay .mistakeImage", image)
                    page.locator("#retryWinMistakesBtn").click()
                    self.assertEqual(page.locator("#mistakeRetryStatus").inner_text(), practice)
                    self.assertTrue(page.locator("#mistakeRetryStatus").is_visible())
                    self.assertEqual(page.locator("#mistakeRetryStatus").evaluate("element => getComputedStyle(element).color"),
                                     "rgb(35, 69, 103)")
                    self.answer_choice(page, "Верный ✓")
                    page.locator("#winOverlay.show").wait_for(state="visible")
                    page.close()

    def test_clean_open_question_has_no_retry_or_stale_review(self):
        self.open_editor()
        for mode in self.GAME_FORMATS:
            with self.subTest(mode=mode):
                page = self.start(mode, [{"type": "open", "q": "Объясни устно"}])
                page.locator("#answers .openContinueBtn").click()
                page.locator("#winOverlay.show").wait_for(state="visible")
                self.assertTrue(page.locator("#retryWinMistakesBtn").is_hidden())
                self.assertTrue(page.locator("#winOverlay details.mistakeReview").is_hidden())
                self.assertEqual(page.locator("#winOverlay .mistakeQuestion").count(), 0)
                page.close()


if __name__ == "__main__":
    unittest.main()
