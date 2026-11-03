"""Preserve TeX delimiters and literal replacement tokens in exported games."""
import base64
import json
import unittest

import test_genially_export as fixtures


class LatexExportTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.GeniallyExportTest.tearDownClass.__func__)
    setUp = fixtures.GeniallyExportTest.setUp
    tearDown = fixtures.GeniallyExportTest.tearDown
    route = fixtures.GeniallyExportTest.route
    open_editor = fixtures.GeniallyExportTest.open_editor
    import_settings = fixtures.GeniallyExportTest.import_settings

    def open_game(self, mode):
        page = self.context.new_page()
        if mode == 'html':
            page.goto(fixtures.ORIGIN + '/embed-host.html')
            page.set_content(self.editor.evaluate('buildGame(false)'))
        else:
            data = json.dumps(self.editor.evaluate('readSettings()')).encode()
            packed = base64.urlsafe_b64encode(data).decode().rstrip('=')
            page.goto(fixtures.ORIGIN + '/game-engine.html#c=' + packed)
        page.locator('#qtext').wait_for()
        return page

    def test_delimiters_and_question_text_survive_export(self):
        self.open_editor()
        examples = [r'Вычисли $$\frac{1}{2}$$', r'Корень \(\sqrt{x}\)',
                    r'Формула \[x^2\]', "Цена $x$; текст $& и $` и $'"]
        for question in examples:
            self.import_settings({'questions': [{'type': 'open', 'q': question}],
                                  'showTitlePage': False, 'sound': False})
            for mode in ['html', 'engine']:
                with self.subTest(mode=mode, question=question):
                    page = self.open_game(mode)
                    # The shared fixture blocks MathJax, so inspect the exact
                    # source handed to the renderer, not a text approximation.
                    self.assertEqual(page.locator('#qtext').inner_text(), question)
                    self.assertEqual(page.evaluate('MathJax.tex.displayMath'),
                                     [[r'\[', r'\]'], ['$$', '$$']])
                    self.assertEqual(page.evaluate('MathJax.tex.inlineMath'),
                                     [[r'\(', r'\)'], ['$', '$']])
                    self.assertEqual(page.locator('script[src*="mathjax"]').count(), 1)
                    page.close()
