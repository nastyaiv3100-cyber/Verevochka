"""Optional rope prize: rendering, persistence, and playable exports."""
import base64
import json
import unittest

import test_genially_export as fixtures


class RopeItemTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.GeniallyExportTest.tearDownClass.__func__)
    setUp = fixtures.GeniallyExportTest.setUp
    tearDown = fixtures.GeniallyExportTest.tearDown
    route = fixtures.GeniallyExportTest.route
    open_editor = fixtures.GeniallyExportTest.open_editor
    import_settings = fixtures.GeniallyExportTest.import_settings

    def assert_prize(self, frame, visible):
        frame.wait_for_function('typeof drawRope === "function" && imgElem.complete && imgElem.naturalWidth > 0 && ropeVertImg.complete && ropeVertImg.naturalWidth > 0')
        counts = frame.evaluate('''() => {
            let prize = 0, rope = 0, fallback = 0;
            const draw = ctx.drawImage, arc = ctx.arc;
            ctx.drawImage = function(image, ...args) {
                if(image === imgElem) prize++;
                if(image === ropeVertImg) rope++;
                return draw.call(this, image, ...args);
            };
            ctx.arc = function(...args) { fallback++; return arc.apply(this, args); };
            try { drawRope(0); } finally { ctx.drawImage = draw; ctx.arc = arc; }
            return {prize, rope, fallback};
        }''')
        self.assertEqual(counts, {'prize': int(visible), 'rope': 1, 'fallback': 0})

    def test_preview_toggle_reload_and_undo(self):
        self.open_editor()
        self.editor.locator('[data-design-tab="game"]').click()
        self.editor.locator('#heroSizeSection').evaluate('(node) => node.open = true')
        self.assertTrue(self.editor.locator('#showRopeItem').is_checked())
        self.assert_prize(self.editor.locator('#preview').element_handle().content_frame(), True)
        frame = self.editor.locator('#preview').element_handle().content_frame()
        with self.editor.expect_event('framenavigated', predicate=lambda changed: changed == frame):
            self.editor.locator('#showRopeItem').uncheck()
        self.editor.wait_for_function('readSettings().showRopeItem === false')
        self.editor.wait_for_timeout(800)
        self.assert_prize(self.editor.locator('#preview').element_handle().content_frame(), False)
        self.editor.locator('#undoEdit').click()
        self.editor.wait_for_function('readSettings().showRopeItem === true')
        self.editor.locator('#redoEdit').click()
        self.editor.wait_for_function('readSettings().showRopeItem === false')
        self.editor.wait_for_timeout(800)
        self.editor.reload()
        self.editor.wait_for_function('typeof readSettings === "function" && readSettings().showRopeItem === false')
        self.assert_prize(self.editor.locator('#preview').element_handle().content_frame(), False)

    def test_html_and_engine_rendering_and_completion(self):
        self.open_editor()
        for enabled in [False, True]:
            self.import_settings({'showRopeItem': enabled, 'showTitlePage': False,
                                  'questions': fixtures.QUESTIONS[:1], 'sound': False})
            for mode in ['html', 'engine', 'legacy-engine']:
                with self.subTest(enabled=enabled, mode=mode):
                    page = self.context.new_page()
                    if mode == 'html':
                        page.goto(fixtures.ORIGIN + '/embed-host.html')
                        page.set_content(self.editor.evaluate('buildGame(false)'))
                    else:
                        config = self.editor.evaluate('readSettings()')
                        if mode == 'legacy-engine':
                            config.pop('showRopeItem')
                        packed = base64.urlsafe_b64encode(json.dumps(config).encode()).decode().rstrip('=')
                        page.goto(fixtures.ORIGIN + '/game-engine.html#c=' + packed)
                    self.assert_prize(page, enabled or mode == 'legacy-engine')
                    page.get_by_role('button', name='Да ✓', exact=True).click()
                    page.locator('#winOverlay.show').wait_for(state='visible')
                    page.close()
