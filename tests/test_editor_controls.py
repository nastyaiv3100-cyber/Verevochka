"""Browser regressions for visible hero pose, size and placement controls.

Use actual exported games as well as the editor preview. The same picture can
serve every pose; its URL must not decide which pose's dimensions are applied.
"""

import base64
import json
from pathlib import Path
import unittest

import test_genially_export as fixtures


class EditorControlsTest(unittest.TestCase):
    # Share the offline HTTPS browser fixture without rerunning its test methods.
    setUpClass = classmethod(fixtures.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.GeniallyExportTest.tearDownClass.__func__)
    setUp = fixtures.GeniallyExportTest.setUp
    tearDown = fixtures.GeniallyExportTest.tearDown
    route = fixtures.GeniallyExportTest.route
    open_editor = fixtures.GeniallyExportTest.open_editor
    import_settings = fixtures.GeniallyExportTest.import_settings

    def open_game(self, mode, settings, freeze=False):
        self.import_settings(settings)
        page = self.context.new_page()
        if freeze:
            # Run the real animation at identical frame times in both pages.
            # Browser clock mocking can retain different fractional RAF phases
            # after navigation, which would compare two different jump points.
            page.add_init_script("""(() => {
                let now = 0, nextId = 0;
                const pending = new Map();
                Object.defineProperty(performance, 'now', {value: () => now});
                window.requestAnimationFrame = callback => {
                    const id = ++nextId; pending.set(id, callback); return id;
                };
                window.cancelAnimationFrame = id => pending.delete(id);
                window.__advanceAnimation = frames => {
                    for(let i = 0; i < frames; i++) {
                        now += 16;
                        const callbacks = [...pending.values()]; pending.clear();
                        for(const callback of callbacks) callback(now);
                    }
                };
            })();""")
        if mode == "standalone":
            page.goto(fixtures.ORIGIN + "/embed-host.html")
            page.set_content(self.editor.evaluate("buildGame(false)"))
        else:
            config = self.editor.evaluate("readSettings()")
            payload = json.dumps(config, ensure_ascii=False).encode("utf-8")
            encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
            page.goto(fixtures.ORIGIN + "/game-engine.html#c=" + encoded)
        page.locator("#startBtn").wait_for()
        return page

    def assert_hero_size(self, page, pose, expected):
        page.wait_for_function("""({pose, expected}) => {
            const hero = document.querySelector('#charGif');
            return hero && hero.dataset.pose === pose &&
                Math.abs(parseFloat(getComputedStyle(hero).width) - expected) < 0.1 &&
                Math.abs(parseFloat(getComputedStyle(hero).height) - expected) < 0.1;
        }""", arg={"pose": pose, "expected": expected})

    def test_exported_game_sizes_follow_pose_even_when_all_pictures_are_identical(self):
        self.open_editor()
        image = fixtures.data_url(fixtures.ROOT / "assets/hero-stand.webp")
        for mode in ["standalone", "engine"]:
            with self.subTest(mode=mode):
                page = self.open_game(mode, {
                    "questions": fixtures.QUESTIONS, "sound": False,
                    "catSize": 132, "ropeHeroSize": 254, "jumpHeroSize": 226,
                    "assetFiles": {key: image for key in ["catStand", "catJump", "catEat"]},
                    "swingAmount": 0,
                })
                page.locator("#startBtn").click()
                self.assert_hero_size(page, "stand", 132)
                self.assertEqual(page.locator("#charGif").get_attribute("src"), image)
                page.get_by_role("button", name="Да ✓", exact=True).click()
                self.assert_hero_size(page, "jump", 226)
                self.assert_hero_size(page, "rope", 254)
                self.assertEqual(page.locator("#qtext").inner_text(), fixtures.SECOND_QUESTION)
                self.assertEqual(page.locator("#charGif").get_attribute("src"), image)
                page.get_by_role("button", name="Да ✓", exact=True).click()
                self.assert_hero_size(page, "jump", 226)
                page.locator("#winOverlay.show").wait_for(state="visible")
                self.assert_hero_size(page, "stand", 132)
                page.close()

    def test_exported_rope_offsets_move_the_hero_by_the_requested_pixels(self):
        self.open_editor()
        for mode in ["standalone", "engine"]:
            with self.subTest(mode=mode):
                positions = []
                for dx, dy in [(0, 0), (37, -29)]:
                    page = self.open_game(mode, {
                        "questions": fixtures.QUESTIONS, "sound": False,
                        "ropeHeroSize": 218, "ropeHeroOffsetX": dx, "ropeHeroOffsetY": dy,
                        "swingAmount": 0,
                    })
                    page.locator("#startBtn").click()
                    page.get_by_role("button", name="Да ✓", exact=True).click()
                    self.assert_hero_size(page, "rope", 218)
                    positions.append(page.locator("#charGif").evaluate("""hero => ({
                        x: parseFloat(hero.style.left), y: parseFloat(hero.style.top)
                    })"""))
                    page.close()
                self.assertAlmostEqual(positions[1]["x"] - positions[0]["x"], 37, delta=0.15)
                self.assertAlmostEqual(positions[1]["y"] - positions[0]["y"], -29, delta=0.15)

    def test_exported_jump_offsets_apply_during_the_actual_transfer(self):
        self.open_editor()
        for mode in ["standalone", "engine"]:
            with self.subTest(mode=mode):
                positions = []
                for dx, dy in [(0, 0), (-33, 21)]:
                    page = self.open_game(mode, {
                        "questions": fixtures.QUESTIONS, "sound": False,
                        "jumpHeroSize": 246, "jumpHeroOffsetX": dx, "jumpHeroOffsetY": dy,
                        "swingAmount": 0,
                    }, freeze=True)
                    page.locator("#startBtn").click()
                    page.get_by_role("button", name="Да ✓", exact=True).click()
                    page.evaluate("__advanceAnimation(5)")
                    self.assert_hero_size(page, "jump", 246)
                    positions.append(page.locator("#charGif").evaluate("""hero => ({
                        x: parseFloat(hero.style.left), y: parseFloat(hero.style.top)
                    })"""))
                    page.close()
                self.assertAlmostEqual(positions[1]["x"] - positions[0]["x"], -33, delta=0.15)
                self.assertAlmostEqual(positions[1]["y"] - positions[0]["y"], 21, delta=0.15)

    def set_range(self, control, value):
        self.editor.locator("#" + control).evaluate("""(input, value) => {
            input.value = value;
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
        }""", str(value))

    def preview_frame(self):
        frame = self.editor.locator("#preview").element_handle().content_frame()
        frame.locator("#charGif").wait_for(state="attached")
        return frame

    def hero_position(self, frame):
        return frame.locator("#charGif").evaluate("""hero => ({
            x: parseFloat(hero.style.left), y: parseFloat(hero.style.top)
        })""")

    def wait_preview_measurement(self):
        frame = self.preview_frame()
        expected = frame.locator("#charGif").evaluate("""hero => ({
            pose: hero.dataset.pose, width: hero.getBoundingClientRect().width
        })""")
        self.editor.wait_for_function("""expected => {
            const iframe = document.querySelector('#preview');
            return previewMeasure?.hero?.pose === expected.pose &&
                Math.abs(previewMeasure.viewport.width - iframe.clientWidth) <= 1 &&
                Math.abs(previewMeasure.hero.width - expected.width) < 0.5;
        }""", arg=expected)

    def drag_handle(self, kind, dx, dy):
        # Scroll the persistent iframe before taking the latest handle
        # coordinates; scrolling can trigger another scene measurement.
        self.editor.locator("#preview").scroll_into_view_if_needed()
        self.wait_preview_measurement()
        handle = self.editor.locator('[data-drag-type="' + kind + '"]')
        bounds = handle.bounding_box()
        self.assertIsNotNone(bounds)
        x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
        frame = self.preview_frame()
        # Pointer release queues a debounced rebuild. Wait for that actual
        # navigation and its new measurement before starting another gesture.
        with self.editor.expect_event("framenavigated", predicate=lambda navigated: navigated == frame):
            self.editor.mouse.move(x, y)
            self.editor.mouse.down()
            self.editor.mouse.move(x + dx, y + dy, steps=4)
            self.editor.mouse.up()
        self.wait_preview_measurement()

    def test_numeric_controls_show_the_selected_pose_and_change_the_visible_hero(self):
        self.open_editor()
        self.editor.locator("#heroSizeSection > summary").click()
        self.editor.locator("#previewHeroPose").select_option("rope")
        frame = self.preview_frame()
        self.assert_hero_size(frame, "rope", 180)
        self.editor.locator("#ropeHeroSizeValue").fill("244")
        self.assert_hero_size(frame, "rope", 244)
        self.assertEqual(self.editor.locator("#ropeHeroSize").input_value(), "244")
        before = self.hero_position(frame)
        self.editor.locator("#ropeHeroOffsetXValue").fill("37")
        self.editor.locator("#ropeHeroOffsetYValue").fill("-23")
        frame.wait_for_function("""before => {
            const hero = document.querySelector('#charGif');
            return hero.dataset.pose === 'rope' &&
                Math.abs(parseFloat(hero.style.left) - before.x - 37) < 0.2 &&
                Math.abs(parseFloat(hero.style.top) - before.y + 23) < 0.2;
        }""", arg=before)
        self.editor.locator("#jumpHeroSizeValue").fill("282")
        self.assert_hero_size(frame, "jump", 282)
        self.assertEqual(self.editor.locator("#previewHeroPose").input_value(), "jump")
        self.assertEqual(self.editor.locator("#ropeHeroSizeValue").input_value(), "244")
        self.editor.locator("#catSizeValue").fill("146")
        self.assert_hero_size(frame, "stand", 146)
        self.assertEqual(self.editor.locator("#previewHeroPose").input_value(), "stand")

    def test_dragging_hero_edits_the_selected_pose_without_moving_the_other_poses(self):
        self.open_editor()
        self.editor.locator("#heroSizeSection > summary").click()
        for pose, prefix, size in [("rope", "ropeHero", 180), ("jump", "jumpHero", 224)]:
            with self.subTest(pose=pose):
                frame = self.preview_frame()
                with self.editor.expect_event("framenavigated", predicate=lambda navigated: navigated == frame):
                    self.editor.locator("#previewHeroPose").select_option(pose)
                    if pose == "jump":
                        self.editor.locator("#jumpHeroSizeValue").fill(str(size))
                self.assert_hero_size(frame, pose, size)
                self.wait_preview_measurement()
                before = self.editor.evaluate("readSettings()")
                self.drag_handle("cat", 18, 12)
                after = self.editor.evaluate("readSettings()")
                self.assertGreater(after[prefix + "OffsetX"], before[prefix + "OffsetX"])
                self.assertGreater(after[prefix + "OffsetY"], before[prefix + "OffsetY"])
                self.assertEqual(after["sceneLayout"], before["sceneLayout"])
                other = "jumpHero" if pose == "rope" else "ropeHero"
                for suffix in ["Size", "OffsetX", "OffsetY"]:
                    self.assertEqual(after[other + suffix], before[other + suffix])
                moved = self.editor.evaluate("readSettings()")
                self.drag_handle("heroSize", 16, 12)
                resized = self.editor.evaluate("readSettings()")
                self.assertGreater(resized[prefix + "Size"], moved[prefix + "Size"])
                self.assertEqual(resized[other + "Size"], moved[other + "Size"])
                self.assertEqual(resized[prefix + "OffsetX"], moved[prefix + "OffsetX"])
                self.assertEqual(resized[prefix + "OffsetY"], moved[prefix + "OffsetY"])
                self.assertEqual(resized["sceneLayout"], moved["sceneLayout"])

    def test_small_card_drag_moves_by_the_drag_delta_without_jumping_to_its_handle(self):
        self.open_editor()
        self.preview_frame().wait_for_function("document.querySelector('#charGif').dataset.pose === 'stand'")
        before = self.editor.evaluate("readSettings().sceneLayout")
        self.drag_handle("cardMove", 0, 10)
        after = self.editor.evaluate("readSettings().sceneLayout")
        self.assertAlmostEqual(after["cardX"], before["cardX"], delta=0.15)
        self.assertGreater(after["cardY"] - before["cardY"], 0.5)
        self.assertLess(after["cardY"] - before["cardY"], 6)
        self.assertEqual((after["catX"], after["catY"]), (before["catX"], before["catY"]))

    def test_entering_edit_mode_during_a_jump_returns_to_a_playable_game(self):
        self.open_editor()
        frame = self.preview_frame()
        self.editor.locator("#togglePreviewEdit").click()
        frame.locator("#startBtn").click()
        frame.get_by_role("button", name="Да ✓", exact=True).click()
        frame.wait_for_function("document.querySelector('#charGif').dataset.pose === 'jump'")
        self.editor.locator("#togglePreviewEdit").click()
        frame.wait_for_function("document.querySelector('#charGif').dataset.pose === 'stand'")
        self.editor.locator("#togglePreviewEdit").click()
        frame.wait_for_function("""expected =>
            document.querySelector('#qtext').textContent === expected &&
            [...document.querySelectorAll('#answers button')].every(button => !button.disabled)
        """, arg=fixtures.FIRST_QUESTION)
        frame.get_by_role("button", name="Да ✓", exact=True).click()
        frame.wait_for_function("expected => document.querySelector('#qtext').textContent === expected",
                                arg=fixtures.SECOND_QUESTION)
        # Repeated layout sync must not restart an already-running game.
        self.editor.evaluate("sendPreviewEditorLayout()")
        frame.wait_for_timeout(100)
        self.assertEqual(frame.locator("#qtext").inner_text(), fixtures.SECOND_QUESTION)
        self.assertTrue(frame.get_by_role("button", name="Да ✓", exact=True).is_enabled())
        frame.get_by_role("button", name="Да ✓", exact=True).click()
        frame.locator("#winOverlay.show").wait_for(state="visible")

    def test_card_width_matches_the_entered_pixel_width(self):
        self.open_editor()
        self.editor.locator("#heroSizeSection > summary").click()
        self.editor.locator("#cardWidth").fill("620")
        frame = self.preview_frame()
        frame.wait_for_function("Math.abs(document.querySelector('.card').getBoundingClientRect().width - 620) < 1")
        self.assertEqual(self.editor.evaluate("readSettings().cardWidth"), 620)

    def test_design_tabs_show_the_selected_screen_in_preview(self):
        self.open_editor()
        frame = self.preview_frame()
        for tab, overlay in [("lose", "overOverlay"), ("win", "winOverlay"), ("title", "startOverlay")]:
            with self.subTest(tab=tab):
                self.editor.locator('[data-design-tab="' + tab + '"]').click()
                frame.locator("#" + overlay + ".show").wait_for(state="visible")
                self.assertEqual(frame.locator(".overlay.show").count(), 1)
        self.editor.locator('[data-design-tab="game"]').click()
        frame.wait_for_function("document.querySelectorAll('.overlay.show').length === 0")

    def test_design_slider_number_and_percentage_restore_together(self):
        self.open_editor()
        self.editor.locator("#titleTransparencyValue").fill("42")
        self.assertEqual(self.editor.locator("#titleTransparency").input_value(), "42")
        self.assertEqual(self.editor.locator("#titleTransparencyOut").text_content(), "42%")
        self.assertEqual(self.editor.evaluate("readSettings().theme.titleTransparency"), 42)
        self.import_settings({"theme": {"titleTransparency": 27}})
        self.assertEqual(self.editor.locator("#titleTransparencyValue").input_value(), "27")
        self.assertEqual(self.editor.locator("#titleTransparencyOut").text_content(), "27%")
        frame = self.preview_frame()
        frame.wait_for_function("""() => {
            const modal = document.querySelector('#startOverlay .startModal');
            return getComputedStyle(modal).backgroundColor.endsWith(', 0.73)');
        }""")

    def test_movement_controls_survive_autosave_and_a_downloaded_project(self):
        self.open_editor()
        self.editor.locator("#heroSizeSection > summary").click()
        values = {
            "foodRotation": -63, "ropeWidth": 142, "fishSize": 126,
            "catSize": 154, "ropeHeroSize": 238,
            "ropeHeroOffsetX": -47, "ropeHeroOffsetY": 31,
            "jumpHeroSize": 284, "jumpHeroOffsetX": 27, "jumpHeroOffsetY": -39,
            "ropeLength": 29, "swingSpeed": 0.85, "swingAmount": 0.17, "lives": 6,
        }
        for control, value in values.items():
            self.set_range(control, value)
        expected = {**values, "ropeLength": 0.29}
        for key, value in expected.items():
            self.assertAlmostEqual(self.editor.evaluate("key => readSettings()[key]", key), value)
        self.editor.wait_for_function("""() => Object.keys(localStorage).some(key => {
            try {
                const saved = JSON.parse(localStorage.getItem(key));
                return saved.settings?.ropeHeroOffsetX === -47 && saved.settings?.lives === 6;
            } catch { return false; }
        })""")
        with self.editor.expect_download() as pending:
            self.editor.locator("#saveConfig").click()
        backup = json.loads(Path(pending.value.path()).read_text(encoding="utf-8"))
        for key, value in expected.items():
            self.assertAlmostEqual(backup[key], value)
        self.editor.reload()
        self.editor.wait_for_function("typeof readSettings === 'function'")
        for control, value in values.items():
            self.assertAlmostEqual(float(self.editor.locator("#" + control).input_value()), value)
            self.assertAlmostEqual(float(self.editor.locator("#" + control + "Value").input_value()), value)
        self.set_range("ropeHeroSize", 104)
        self.import_settings(backup)
        for control, value in values.items():
            self.assertAlmostEqual(float(self.editor.locator("#" + control).input_value()), value)


if __name__ == "__main__":
    unittest.main()
