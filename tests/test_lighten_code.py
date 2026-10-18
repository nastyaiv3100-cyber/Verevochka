"""Browser regressions for the image optimization and undo controls."""

import base64
import copy
import json
import struct
import unittest
import zlib

import test_genially_export as export_tests


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def animated_png():
    """Two valid RGBA frames, including the APNG control chunks."""
    header = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
    def frame_control(sequence):
        return struct.pack(">IIIIIHHBB", sequence, 2, 2, 0, 0, 1, 10, 0, 0)
    first = zlib.compress((b"\x00" + b"\xff\x00\x00\xff" * 2) * 2)
    second = zlib.compress((b"\x00" + b"\x00\x00\xff\xff" * 2) * 2)
    binary = b"\x89PNG\r\n\x1a\n" + b"".join([
        png_chunk(b"IHDR", header), png_chunk(b"acTL", struct.pack(">II", 2, 0)),
        png_chunk(b"fcTL", frame_control(0)), png_chunk(b"IDAT", first),
        png_chunk(b"fcTL", frame_control(1)),
        png_chunk(b"fdAT", struct.pack(">I", 2) + second), png_chunk(b"IEND", b""),
    ])
    return "data:image/png;base64," + base64.b64encode(binary).decode("ascii")


def animated_webp(static_data_url):
    """Wrap a browser-produced opaque WebP frame into a two-frame animation."""
    static = base64.b64decode(static_data_url.split(",", 1)[1])
    frame = b""
    offset = 12
    while offset + 8 <= len(static):
        length = struct.unpack_from("<I", static, offset + 4)[0]
        end = offset + 8 + length + length % 2
        if static[offset:offset + 4] in (b"ALPH", b"VP8 ", b"VP8L"):
            frame += static[offset:end]
        offset = end
    def chunk(kind, data):
        return kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")
    # VP8X dimensions and ANMF dimensions store width/height minus one.
    size = b"\x01\x00\x00"
    control = b"\x02\x00\x00\x00" + size + size
    frame_header = b"\x00" * 6 + size + size + b"\x64\x00\x00\x00"
    body = b"WEBP" + chunk(b"VP8X", control) + chunk(b"ANIM", b"\x00" * 6)
    body += chunk(b"ANMF", frame_header + frame) * 2
    binary = b"RIFF" + struct.pack("<I", len(body)) + body
    return "data:image/webp;base64," + base64.b64encode(binary).decode("ascii")


class LightenCodeTest(unittest.TestCase):
    # Share the offline HTTPS routing and real-iframe helpers without inheriting
    # the five independent export tests (which discovery already runs once).
    setUpClass = classmethod(export_tests.GeniallyExportTest.setUpClass.__func__)
    tearDownClass = classmethod(export_tests.GeniallyExportTest.tearDownClass.__func__)
    setUp = export_tests.GeniallyExportTest.setUp
    tearDown = export_tests.GeniallyExportTest.tearDown
    route = export_tests.GeniallyExportTest.route
    open_editor = export_tests.GeniallyExportTest.open_editor
    import_settings = export_tests.GeniallyExportTest.import_settings
    export_code = export_tests.GeniallyExportTest.export_code
    load_iframe = export_tests.GeniallyExportTest.load_iframe
    assert_image = export_tests.GeniallyExportTest.assert_image

    def images(self):
        return self.editor.evaluate("""() => {
            const canvas = document.createElement('canvas');
            canvas.width = 1600; canvas.height = 900;
            const ctx = canvas.getContext('2d');
            const pixels = ctx.createImageData(canvas.width, canvas.height);
            for (let y=0; y<canvas.height; y++) for (let x=0; x<canvas.width; x++) {
                const i = (y*canvas.width+x)*4;
                const noise = (((x>>3)*73)^((y>>3)*151))&31;
                pixels.data[i] = (x/8+noise)%256;
                pixels.data[i+1] = (y/5+noise)%256;
                pixels.data[i+2] = (x/16+y/12+noise)%256;
                pixels.data[i+3] = (x<80||y<45) ? 0 : ((x<160||y<90) ? 120 : 255);
            }
            ctx.putImageData(pixels,0,0);
            const images = {png:canvas.toDataURL('image/png'),
                jpeg:canvas.toDataURL('image/jpeg',.98), webp:canvas.toDataURL('image/webp',.98)};
            canvas.width=2; canvas.height=2;
            ctx.fillStyle='red'; ctx.fillRect(0,0,2,2);
            images.tinyWebp=canvas.toDataURL('image/webp');
            images.tinyPng=canvas.toDataURL('image/png');
            return images;
        }""")

    def settings(self):
        return self.editor.evaluate("readSettings()")

    def packed_size(self):
        return self.editor.evaluate("async () => (await prepareGeniallyPayload(readSettings())).packedBytes")

    def lighten(self, selector="#lightenCode"):
        self.editor.locator(selector).click()
        self.editor.wait_for_function("""() => {
            const button=document.querySelector('#lightenCode');
            const notice=document.querySelector('#lightenNotice');
            return !button.disabled && !notice.hidden &&
                document.querySelector('#lightenStatus').textContent.trim().length>0;
        }""", timeout=30000)

    def assert_optimized(self, original, optimized, alpha=False, dimensions=(1280, 720)):
        self.assertTrue(optimized.startswith("data:image/webp;base64,"))
        self.assertLess(len(optimized), len(original))
        metrics = self.editor.evaluate("""async data => {
            const image=new Image();image.src=data;await image.decode();
            const canvas=document.createElement('canvas');
            canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
            const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);
            return {width:image.naturalWidth,height:image.naturalHeight,
                corner:ctx.getImageData(0,0,1,1).data[3],
                partial:ctx.getImageData(Math.min(100,canvas.width-1),Math.min(60,canvas.height-1),1,1).data[3],
                center:ctx.getImageData(Math.floor(canvas.width/2),Math.floor(canvas.height/2),1,1).data[3]};
        }""", optimized)
        self.assertEqual((metrics["width"], metrics["height"]), dimensions)
        if alpha:
            self.assertEqual((metrics["corner"], metrics["partial"], metrics["center"]), (0, 120, 255))

    def test_all_image_locations_shrink_and_survive_preview_and_genially_game(self):
        self.open_editor()
        images = self.images()
        config = self.settings()
        config["theme"]["titleImageData"] = images["png"]
        config["theme"]["titleImageEnabled"] = True
        config["assetFiles"]["catStand"] = images["jpeg"]
        config["assetOverrides"]["food"] = images["webp"]
        remote = export_tests.ORIGIN + "/assets/rope-vertical.webp"
        config["assetOverrides"]["ropeV"] = remote
        config["questions"][0]["image"] = images["png"]
        config["feedbackImages"] = {"win": images["webp"], "lose": images["jpeg"]}
        config["winImageEnabled"] = config["loseImageEnabled"] = True
        config["soundEffects"]["correct"] = "data:audio/wav;base64," + base64.b64encode(export_tests.short_wav()).decode("ascii")
        self.import_settings(config)
        before = self.settings()
        original_packed_size = self.packed_size()
        self.lighten()
        after = self.settings()
        self.assertLess(self.packed_size(), original_packed_size)
        self.assertTrue(self.editor.locator("#undoLightenCode").is_visible())
        self.assert_optimized(images["png"], after["theme"]["titleImageData"], alpha=True)
        self.assert_optimized(images["jpeg"], after["assetFiles"]["catStand"])
        self.assert_optimized(images["webp"], after["assetOverrides"]["food"], alpha=True)
        self.assertEqual(after["questions"][0]["image"], after["theme"]["titleImageData"])
        self.assertEqual(after["feedbackImages"]["win"], after["assetOverrides"]["food"])
        self.assertEqual(after["feedbackImages"]["lose"], after["assetFiles"]["catStand"])
        self.assertEqual(after["assetOverrides"]["ropeV"], remote)
        self.assertEqual(after["soundEffects"], before["soundEffects"])
        self.assertEqual(after["startText"], before["startText"])
        self.assertEqual(after["questions"][0]["q"], export_tests.FIRST_QUESTION)

        preview = self.editor.locator("#preview").element_handle().content_frame()
        self.assert_image(preview, "#titleCat", after["theme"]["titleImageData"])
        host, game, _ = self.load_iframe(self.export_code())
        self.assert_image(game, "#titleCat", after["theme"]["titleImageData"])
        self.assert_image(game, "#winResultImage", after["feedbackImages"]["win"])
        self.assert_image(game, "#loseResultImage", after["feedbackImages"]["lose"])
        game.locator("#startBtn").click()
        self.assert_image(game, "#questionImage", after["questions"][0]["image"])
        self.assert_image(game, "#charGif", after["assetFiles"]["catStand"])
        game.get_by_role("button", name="Да ✓", exact=True).click()
        game.wait_for_function("document.querySelector('#qtext').textContent === " + json.dumps(export_tests.SECOND_QUESTION))
        self.assertTrue(game.evaluate("source => window.__playedAudioSources.includes(source)", after["soundEffects"]["correct"]))
        game.get_by_role("button", name="Да ✓", exact=True).click()
        game.locator("#winOverlay.show").wait_for(state="visible")
        host.close()

    def test_repeated_click_is_lossless_and_undo_preserves_a_later_upload(self):
        self.open_editor()
        images = self.images()
        config = self.settings()
        config["theme"]["titleImageData"] = images["png"]
        config["questions"][0]["image"] = images["png"]
        self.import_settings(config)
        self.lighten()
        optimized = self.settings()
        code = self.export_code()
        self.lighten("#lightenCodeExport")
        self.assertEqual(self.settings(), optimized, "Repeated optimization must not recompress its own lossy output")
        self.assertEqual(self.export_code(), code)
        self.editor.locator("#titleImageFile").set_input_files({
            "name": "later.jpg", "mimeType": "image/jpeg",
            "buffer": base64.b64decode(images["jpeg"].split(",", 1)[1]),
        })
        self.editor.wait_for_function("expected => readSettings().theme.titleImageData === expected", arg=images["jpeg"])
        self.editor.locator("#undoLightenCode").click()
        undone = self.settings()
        self.assertEqual(undone["theme"]["titleImageData"], images["jpeg"], "Undo must preserve a new image uploaded after optimization")
        self.assertEqual(undone["questions"][0]["image"], images["png"])
        self.assertFalse(self.editor.locator("#undoLightenCode").is_visible())

    def test_undo_restores_images_from_two_successful_optimization_passes(self):
        self.open_editor()
        images = self.images()
        self.import_settings({"theme": {"titleImageData": images["png"]}})
        self.lighten()
        optimized_title = self.settings()["theme"]["titleImageData"]
        self.assertNotEqual(optimized_title, images["png"])
        self.editor.locator("#file-catStand").set_input_files({
            "name": "second-image.jpg", "mimeType": "image/jpeg",
            "buffer": base64.b64decode(images["jpeg"].split(",", 1)[1]),
        })
        self.editor.wait_for_function("expected => readSettings().assetFiles.catStand === expected", arg=images["jpeg"])
        self.lighten()
        optimized = self.settings()
        self.assertEqual(optimized["theme"]["titleImageData"], optimized_title)
        self.assert_optimized(images["jpeg"], optimized["assetFiles"]["catStand"])
        self.editor.locator("#undoLightenCode").click()
        undone = self.settings()
        self.assertEqual(undone["theme"]["titleImageData"], images["png"])
        self.assertEqual(undone["assetFiles"]["catStand"], images["jpeg"])
        self.assertFalse(self.editor.locator("#undoLightenCode").is_visible())

    def test_undo_survives_question_type_and_quick_editor_changes(self):
        self.open_editor()
        images = self.images()
        config = self.settings()
        config["questions"][0]["image"] = images["png"]
        for operation in ["type", "quick"]:
            with self.subTest(operation=operation):
                self.import_settings(config)
                self.lighten()
                optimized = self.settings()["questions"][0]["image"]
                self.assertNotEqual(optimized, images["png"])
                if operation == "type":
                    self.editor.locator("#modeCards").click()
                    self.editor.locator(".qType").first.select_option("open")
                    expected_type = "open"
                    expected_text = export_tests.FIRST_QUESTION
                else:
                    self.editor.locator("#modeQuick").click()
                    self.editor.locator("#quickQuestions").fill(f"[CHOICE] {export_tests.FIRST_QUESTION} | кот | собака\n[CHOICE] {export_tests.SECOND_QUESTION} | Да ✓ | Нет")
                    self.editor.locator("#applyQuickQuestions").click()
                    expected_type = "choice"
                    expected_text = export_tests.FIRST_QUESTION
                edited = self.settings()["questions"][0]
                self.assertEqual(edited["type"], expected_type)
                self.assertEqual(edited["q"], expected_text)
                self.assertEqual(edited["image"], optimized)
                self.editor.locator("#undoLightenCode").click()
                restored = self.settings()["questions"][0]
                self.assertEqual(restored["image"], images["png"])
                self.assertEqual(restored["type"], expected_type)
                self.assertEqual(restored["q"], expected_text)
                if operation == "quick":
                    self.assertEqual(restored["a"], ["кот", "собака"])
                self.assertFalse(self.editor.locator("#undoLightenCode").is_visible())

    def test_animation_and_failed_images_are_untouched_while_other_images_shrink(self):
        self.open_editor()
        images = self.images()
        config = self.settings()
        config["theme"]["titleImageData"] = images["png"]
        config["assetFiles"]["catStand"] = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
        config["assetOverrides"]["food"] = "data:image/svg+xml;base64," + base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><path d="M0 0h2v2H0z" fill="red"/></svg>').decode("ascii")
        config["questions"][0]["image"] = animated_png()
        config["questions"][1]["image"] = "data:image/png;base64,bm90LWFuLWltYWdl"
        config["feedbackImages"] = {"win": animated_webp(images["tinyWebp"]), "lose": export_tests.ORIGIN + "/assets/hero-jump.webp"}
        self.import_settings(config)
        before = self.settings()
        # The animation fixtures must be genuine images, rather than malformed
        # payloads that would pass this check through generic decode failure.
        for image in [before["questions"][0]["image"], before["feedbackImages"]["win"]]:
            self.assertTrue(self.editor.evaluate("async src => {const image=new Image();image.src=src;await image.decode();return image.naturalWidth===2}", image))
        self.lighten()
        after = self.settings()
        self.assertNotEqual(after["theme"]["titleImageData"], before["theme"]["titleImageData"])
        for key in ["assetFiles", "assetOverrides", "questions", "feedbackImages"]:
            self.assertEqual(after[key], before[key], key + " must preserve animations, remote URLs, and failed images")

    def test_no_uploaded_images_and_import_clear_the_undo_state(self):
        self.open_editor()
        baseline = self.settings()
        self.lighten()
        self.assertEqual(self.settings(), baseline)
        self.assertFalse(self.editor.locator("#undoLightenCode").is_visible())
        images = self.images()
        tiny_config = copy.deepcopy(baseline)
        tiny_config["theme"]["titleImageData"] = images["tinyPng"]
        self.import_settings(tiny_config)
        self.lighten()
        self.assertEqual(self.settings(), tiny_config, "Keep an original when WebP would make it bigger")
        self.assertFalse(self.editor.locator("#undoLightenCode").is_visible())
        config = copy.deepcopy(baseline)
        config["theme"]["titleImageData"] = images["png"]
        self.import_settings(config)
        self.lighten()
        self.assertTrue(self.editor.locator("#undoLightenCode").is_visible())
        self.import_settings(baseline)
        self.assertEqual(self.settings(), baseline)
        self.assertFalse(self.editor.locator("#undoLightenCode").is_visible())

    def test_small_images_are_never_upscaled(self):
        self.open_editor()
        images = self.images()
        small = self.editor.evaluate("""async data => {
            const image=new Image();image.src=data;await image.decode();
            const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;
            canvas.getContext('2d').drawImage(image,0,0,160,90);
            return canvas.toDataURL('image/png');
        }""", images["png"])
        self.import_settings({"theme": {"titleImageData": small}})
        self.lighten()
        self.assert_optimized(small, self.settings()["theme"]["titleImageData"], dimensions=(160, 90))


if __name__ == "__main__":
    unittest.main()
