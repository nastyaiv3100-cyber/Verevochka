"""Browser regressions for media inside exported Genially iframe links.

Run: python -m unittest discover -s tests -v
Requires Python Playwright and Chromium; no server or external network is used.
"""

import base64
import gzip
import io
import json
import mimetypes
import os
from pathlib import Path
import random
import shutil
import unittest
from urllib.parse import unquote, urlsplit
import wave

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://verevochka.test"
FIRST_QUESTION = "Картинка: ёжик, 猫 и 🐈 — выбери ответ"
SECOND_QUESTION = "Второй вопрос: всё сохранилось?"
QUESTIONS = [
    {"type": "choice", "q": FIRST_QUESTION, "a": ["Да ✓", "Нет", "Не знаю"], "correct": 0},
    {"type": "choice", "q": SECOND_QUESTION, "a": ["Да ✓", "Нет", "Не знаю"], "correct": 0},
]


def data_url(path):
    mime = mimetypes.guess_type(str(path))[0]
    return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def short_wav():
    """A real, short PCM sound, generated without a binary fixture dependency."""
    output = io.BytesIO()
    with wave.open(output, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(1)
        sound.setframerate(8000)
        sound.writeframes(bytes(160 if i % 20 < 10 else 96 for i in range(800)))
    return output.getvalue()


class GeniallyExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium")
        options = {"headless": True}
        if executable:
            options["executable_path"] = executable
        cls.browser = cls.playwright.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.context.set_default_timeout(15000)
        self.engine_requests = []
        self.page_errors = []
        self.context.on("page", lambda page: page.on("pageerror", lambda error: self.page_errors.append(str(error))))
        self.context.route("**/*", self.route)
        # Observe actual use of uploaded sounds without changing media playback.
        self.context.add_init_script("""(() => {
            window.__playedAudioSources = [];
            const NativeAudio = window.Audio;
            window.Audio = function(src) {
                window.__playedAudioSources.push(src);
                return new NativeAudio(src);
            };
            window.Audio.prototype = NativeAudio.prototype;
        })();""")
        self.editor = self.context.new_page()

    def tearDown(self):
        try:
            self.assertEqual(self.page_errors, [], "Export or gameplay caused a JavaScript exception")
        finally:
            self.context.close()

    def route(self, route):
        request_url = urlsplit(route.request.url)
        if request_url.netloc != "verevochka.test":
            # Fonts and MathJax are optional for these media/export checks.
            route.abort()
            return
        if request_url.path == "/embed-host.html":
            route.fulfill(content_type="text/html", body="<!doctype html><html><body></body></html>")
            return
        relative = unquote(request_url.path).lstrip("/") or "index.html"
        path = (ROOT / relative).resolve()
        if ROOT not in path.parents or not path.is_file():
            route.fulfill(status=404, body="Not found")
            return
        if path.name == "game-engine.html":
            self.engine_requests.append(request_url)
        route.fulfill(path=str(path), content_type=mimetypes.guess_type(str(path))[0] or "application/octet-stream")

    def open_editor(self, raw_fallback=False):
        if raw_fallback:
            self.context.add_init_script("window.CompressionStream = undefined;")
        self.editor.goto(ORIGIN + "/index.html")
        self.editor.wait_for_function("typeof readSettings === 'function'")
        self.import_settings({"questions": QUESTIONS, "shuffleQuestions": False, "sound": True})

    def import_settings(self, settings):
        self.editor.locator("#loadConfig").set_input_files({
            "name": "regression-settings.json",
            "mimeType": "application/json",
            "buffer": json.dumps(settings, ensure_ascii=False).encode("utf-8"),
        })
        self.editor.wait_for_function("document.querySelector('#loadConfig').value === ''")

    def export_code(self):
        self.editor.locator('[data-editor-tab="export"]').click()
        self.editor.wait_for_function("!document.querySelector('#copyGeniallyCode').disabled")
        self.assertTrue(self.editor.locator("#geniallyWarning").is_hidden(), "A usable media export should not show a warning")
        return self.editor.locator("#geniallyEmbedCode").input_value()

    def load_iframe(self, code):
        host = self.context.new_page()
        host.goto(ORIGIN + "/embed-host.html")
        host.set_content(code)
        host.wait_for_function("""() => {
            const iframe = document.querySelector('iframe');
            return iframe && iframe.contentDocument && iframe.contentDocument.querySelector('#startBtn');
        }""")
        iframe = host.locator("iframe")
        frame = iframe.element_handle().content_frame()
        return host, frame, urlsplit(iframe.get_attribute("src"))

    def assert_image(self, frame, selector, expected):
        frame.wait_for_function("""({selector, expected}) => {
            const img = document.querySelector(selector);
            return img && img.src === expected && img.complete && img.naturalWidth > 0;
        }""", arg={"selector": selector, "expected": expected})

    def test_uploaded_webp_images_and_sound_survive_real_iframe_and_gameplay(self):
        self.open_editor()
        image_paths = {
            "title": ROOT / "assets/hero-stand.webp",
            "hero": ROOT / "assets/food.webp",
            "question": ROOT / "assets/editor-logo.webp",
            "win": ROOT / "assets/hero-eat.webp",
            "lose": ROOT / "assets/hero-jump.webp",
        }
        self.editor.locator("#titleImageFile").set_input_files(image_paths["title"])
        self.editor.locator("#file-catStand").set_input_files(image_paths["hero"])
        self.editor.locator(".qImageFile").first.set_input_files(image_paths["question"])
        self.editor.locator("#winImageFile").set_input_files(image_paths["win"])
        self.editor.locator("#loseImageFile").set_input_files(image_paths["lose"])
        sound = short_wav()
        expected_sound = "data:audio/wav;base64," + base64.b64encode(sound).decode("ascii")
        self.editor.locator("#correctSoundFile").set_input_files({"name": "answer.wav", "mimeType": "audio/wav", "buffer": sound})
        self.editor.wait_for_function("document.querySelector('#correctSoundPreview').src.startsWith('data:audio/')")

        code = self.export_code()
        host, game, url = self.load_iframe(code)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.path, "/game-engine.html")
        self.assertEqual(url.query, "", "New links must not put large media into server query strings")
        self.assertTrue(url.fragment.startswith("z="), "Chromium should produce compressed settings")
        self.assertGreater(len(url.geturl()), 7000, "Fixture must exceed the old export limit")
        self.assertLess(len(url.geturl()), 1024 * 1024)
        self.assertTrue(self.engine_requests, "The exported iframe must actually request the engine")
        self.assertTrue(all(not request.query for request in self.engine_requests))

        for kind, selector in [("title", "#titleCat"), ("win", "#winResultImage"), ("lose", "#loseResultImage")]:
            self.assert_image(game, selector, data_url(image_paths[kind]))
        game.locator("#startBtn").click()
        self.assertEqual(game.locator("#qtext").inner_text(), FIRST_QUESTION)
        self.assert_image(game, "#questionImage", data_url(image_paths["question"]))
        self.assert_image(game, "#charGif", data_url(image_paths["hero"]))
        game.get_by_role("button", name="Да ✓", exact=True).click()
        game.wait_for_function("document.querySelector('#qtext').textContent === " + json.dumps(SECOND_QUESTION))
        self.assertTrue(game.evaluate("expected => window.__playedAudioSources.includes(expected)", expected_sound), "Uploaded correct-answer audio must reach real playback")
        game.get_by_role("button", name="Да ✓", exact=True).click()
        game.locator("#winOverlay.show").wait_for(state="visible")
        self.assert_image(game, "#winResultImage", data_url(image_paths["win"]))
        game.locator("#playAgainBtn").click()
        for _ in range(3):
            game.get_by_role("button", name="Нет", exact=True).click()
        game.locator("#overOverlay.show").wait_for(state="visible")
        self.assert_image(game, "#loseResultImage", data_url(image_paths["lose"]))
        host.close()

    def test_raw_export_fallback_still_contains_uploaded_image(self):
        self.open_editor(raw_fallback=True)
        image = ROOT / "assets/editor-logo.webp"
        self.editor.locator("#titleImageFile").set_input_files(image)
        self.editor.wait_for_function("document.querySelector('#titleImagePreview').src.startsWith('data:image/')")
        host, game, url = self.load_iframe(self.export_code())
        self.assertEqual(url.query, "")
        self.assertTrue(url.fragment.startswith("c="))
        self.assertGreater(len(url.geturl()), 7000)
        self.assert_image(game, "#titleCat", data_url(image))
        host.close()

    def test_legacy_queries_and_new_fragments_render_unicode_and_embedded_media(self):
        self.open_editor()
        config = self.editor.evaluate("readSettings()")
        image = data_url(ROOT / "assets/editor-logo.webp")
        config["theme"]["titleImageData"] = image
        config["questions"][0]["image"] = image
        payload = json.dumps(config, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        for mode, compressed in [("c", False), ("z", True)]:
            encoded = base64.urlsafe_b64encode(gzip.compress(payload) if compressed else payload).decode("ascii").rstrip("=")
            for location in ["query", "fragment", "query_with_anchor"]:
                with self.subTest(mode=mode, location=location):
                    suffix = ("#" if location == "fragment" else "?") + mode + "=" + encoded
                    if location == "query_with_anchor":
                        suffix += "#section"
                    game = self.context.new_page()
                    game.goto(ORIGIN + "/game-engine.html" + suffix)
                    game.locator("#startBtn").wait_for()
                    self.assert_image(game, "#titleCat", image)
                    game.locator("#startBtn").click()
                    self.assertEqual(game.locator("#qtext").inner_text(), FIRST_QUESTION)
                    self.assert_image(game, "#questionImage", image)
                    game.close()

        # A recognized fragment must take priority over stale query settings.
        query_config = {**config, "startTitle": "Старый заголовок из query"}
        fragment_config = {**config, "startTitle": "Новый заголовок из фрагмента 🐈"}
        query_encoded = base64.urlsafe_b64encode(json.dumps(query_config, ensure_ascii=False).encode()).decode().rstrip("=")
        fragment_encoded = base64.urlsafe_b64encode(gzip.compress(json.dumps(fragment_config, ensure_ascii=False).encode())).decode().rstrip("=")
        game = self.context.new_page()
        game.goto(ORIGIN + "/game-engine.html?c=" + query_encoded + "#z=" + fragment_encoded)
        game.locator("#startBtn").wait_for()
        self.assertEqual(game.locator("#startOverlay h1").inner_text(), fragment_config["startTitle"])
        game.close()

    def test_large_export_warns_without_blocking_or_truncating_the_iframe(self):
        self.open_editor()
        self.assertIn("<iframe", self.export_code())
        # Incompressible user text exceeds the real warning threshold without
        # changing production constants or stubbing the packing function.
        large_text = base64.b64encode(random.Random(314159).randbytes(1100000)).decode("ascii")
        self.import_settings({"startText": large_text})
        self.editor.wait_for_function("""() => {
            const warning = document.querySelector('#geniallyWarning');
            return !warning.hidden && !document.querySelector('#copyGeniallyCode').disabled &&
                document.querySelector('#geniallyEmbedCode').value.startsWith('<iframe');
        }""", timeout=30000)
        code = self.editor.locator("#geniallyEmbedCode").input_value()
        source = self.editor.evaluate("""code => new DOMParser()
            .parseFromString(code, 'text/html').querySelector('iframe').getAttribute('src')""", code)
        url = urlsplit(source)
        self.assertGreater(len(source), 1024 * 1024)
        self.assertEqual(url.query, "")
        self.assertTrue(url.fragment.startswith("z="))
        encoded = url.fragment.split("=", 1)[1]
        payload = gzip.decompress(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        self.assertEqual(json.loads(payload)["startText"], large_text)
        self.assertRegex(self.editor.locator("#geniallyWarningTitle").inner_text().lower(), "больш")
        self.assertIn("доступен для копирования", self.editor.locator("#geniallyWarningText").inner_text())
        self.editor.evaluate("""() => {
            window.__largeClipboard = null;
            Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{
                writeText(text) { window.__largeClipboard = text; return Promise.resolve(); }
            }});
        }""")
        self.editor.locator("#copyGeniallyCode").click()
        self.editor.wait_for_function("window.__largeClipboard !== null")
        self.assertEqual(self.editor.evaluate("window.__largeClipboard"), code)
        self.assertTrue(self.editor.locator("#downloadGame").is_enabled())
        # Returning below the threshold clears the warning, too.
        self.import_settings({"startText": "Короткий текст"})
        self.assertIn("<iframe", self.export_code())

    def test_http_editor_explains_why_genially_export_requires_https(self):
        self.editor.goto("http://verevochka.test/index.html")
        self.editor.locator('[data-editor-tab="export"]').click()
        self.editor.locator("#geniallyWarning").wait_for(state="visible")
        self.assertIn("HTTPS", self.editor.locator("#geniallyWarning").inner_text())
        self.assertTrue(self.editor.locator("#copyGeniallyCode").is_disabled())
        self.assertEqual(self.editor.locator("#geniallyEmbedCode").input_value(), "")
        self.assertTrue(self.editor.locator("#downloadGame").is_enabled())

    def test_large_uncompressed_fallback_is_also_available_with_a_warning(self):
        self.open_editor(raw_fallback=True)
        large_text = base64.b64encode(random.Random(271828).randbytes(650000)).decode("ascii")
        self.import_settings({"startText": large_text})
        self.editor.locator('[data-editor-tab="export"]').click()
        self.editor.wait_for_function("""() => !document.querySelector('#copyGeniallyCode').disabled &&
            !document.querySelector('#geniallyWarning').hidden""", timeout=30000)
        code = self.editor.locator("#geniallyEmbedCode").input_value()
        source = self.editor.evaluate("""code => new DOMParser().parseFromString(code, 'text/html')
            .querySelector('iframe').getAttribute('src')""", code)
        self.assertGreater(len(source), 1024 * 1024)
        fragment = urlsplit(source).fragment
        self.assertTrue(fragment.startswith("c="))
        encoded = fragment.split("=", 1)[1]
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        self.assertEqual(json.loads(payload)["startText"], large_text)


if __name__ == "__main__":
    unittest.main()
