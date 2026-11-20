"""Offline tests for the story image prompts and the video pipeline.

Run from the repository root:  python -m unittest discover -s tests -v
No network, API key or FTP server is needed (FFmpeg is needed for the video test).
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import image_prompts as ip  # noqa: E402


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STORY = {
    "story_code": "CH-666-0001",
    "title": "測試故事",
    "summary": "摘要",
    "category": "6",
    "horror_type": ["surveillance_horror", "psychological"],
    "fantasy_level": "slightly_unreal",
    "dice_seed": 12345,
    "director_analysis": {"anomaly_core": "a", "character_core": "b", "internal_rule": "c"},
    "content": "<p><strong>第一章｜開始</strong></p>"
    + "".join(f"<p>這是第{i}段，長度足夠用來測試場景選取是否正常運作，並且包含一些描述文字。</p>" for i in range(1, 11)),
}


class ImagePromptTests(unittest.TestCase):
    def test_headings_are_not_used_as_beats(self):
        beats = ip.story_beats(STORY)
        self.assertEqual(set(beats), {"opening", "turning point", "climax"})
        self.assertFalse(any("第一章" in text for text in beats.values()))

    def test_plan_is_deterministic_and_has_expected_kinds(self):
        a = ip.plan_images(STORY, "6", {})
        b = ip.plan_images(STORY, "6", {})
        self.assertEqual(a, b)
        self.assertEqual([p["kind"] for p in a], ["cover", "scene"])
        extended = ip.plan_images(STORY, "6", {}, extra_scenes=True)
        self.assertEqual([p["kind"] for p in extended], ["cover", "scene_open", "scene", "scene_end"])

    def test_images_of_one_story_differ_in_shot_and_light(self):
        plan = ip.plan_images(STORY, "6", {}, extra_scenes=True)
        self.assertEqual(len({p["prompt"] for p in plan}), 4)
        shots = [next(s for s in ip.SHOTS if s[0].upper() + s[1:] in p["prompt"]) for p in plan]
        self.assertEqual(len(set(shots)), 4)

    def test_different_stories_get_different_looks(self):
        seen = set()
        for seed in range(40):
            story = dict(STORY, story_code=f"CH-666-{seed:04d}", dice_seed=seed)
            seen.add(ip.plan_images(story, "6", {})[0]["prompt"].split("Colour palette: ")[1].split(".")[0])
        self.assertGreaterEqual(len(seen), 4)

    def test_llm_scene_is_used_and_chinese_is_rejected(self):
        def ask(system, user):
            return {"images": [
                {"kind": "cover", "scene": "An empty witness chair under a bare bulb."},
                {"kind": "scene", "scene": "這是中文描述，不應被接受"},
                {"kind": "bogus", "scene": "Ignored kind."},
            ]}

        plan = ip.plan_images(STORY, "6", {}, ask=ask)
        self.assertEqual([p["source"] for p in plan], ["llm", "fallback"])
        self.assertIn("An empty witness chair", plan[0]["prompt"])

    def test_llm_failure_never_raises(self):
        def boom(system, user):
            raise RuntimeError("provider down")

        plan = ip.plan_images(STORY, "6", {}, ask=boom)
        self.assertEqual([p["source"] for p in plan], ["fallback", "fallback"])

    def test_prompts_are_english_only_and_bounded(self):
        for cat in ("3", "6", "9"):
            for p in ip.plan_images(STORY, cat, {}, extra_scenes=True):
                self.assertFalse(ip.CJK.search(p["prompt"]), p["prompt"])
                self.assertLessEqual(len(p["prompt"]), 1200)


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gsv = load_script("generate_story_videos")

    class Resp:
        def __init__(self, status=200, body=b"", headers=None):
            self.status_code, self._body, self.headers = status, body, headers or {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_content(self, chunk_size=0):
            yield self._body

    def session(self, *responses):
        s = mock.Mock()
        s.get.side_effect = list(responses)
        return s

    def test_http_403_message_names_status_and_host(self):
        s = self.session(self.Resp(403, b"", {"Content-Type": "text/html"}))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError) as ctx:
            self.gsv.download_image(s, "https://example.com/images/a.webp", Path(tmp) / "x.webp")
        self.assertIn("HTTP 403", str(ctx.exception))
        self.assertIn("example.com", str(ctx.exception))

    def test_html_block_page_is_reported_as_not_an_image(self):
        s = self.session(self.Resp(200, b"<html>Just a moment...</html>", {"Content-Type": "text/html"}))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError) as ctx:
            self.gsv.download_image(s, "https://example.com/images/a.webp", Path(tmp) / "x.webp")
        self.assertIn("not a valid image", str(ctx.exception))

    def test_redirect_to_other_host_is_refused_same_host_is_followed(self):
        s = self.session(self.Resp(302, b"", {"Location": "https://evil.example.net/x.webp"}))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError) as ctx:
            self.gsv.download_image(s, "https://example.com/images/a.webp", Path(tmp) / "x.webp")
        self.assertIn("another host", str(ctx.exception))

        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, "WEBP")
        s = self.session(self.Resp(301, b"", {"Location": "/images/b.webp"}), self.Resp(200, buf.getvalue()))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "x.webp"
            self.gsv.download_image(s, "https://example.com/images/a.webp", target)
            self.assertGreater(target.stat().st_size, 0)

    def test_browser_user_agent_is_sent(self):
        s = self.session(self.Resp(404))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            self.gsv.download_image(s, "https://example.com/images/a.webp", Path(tmp) / "x.webp")
        self.assertIn("Mozilla", s.get.call_args.kwargs["headers"]["User-Agent"])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class VideoPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gsv = load_script("generate_story_videos")
        cls.story_video = load_script("story_video")

    def make_image(self, path, color):
        from PIL import Image
        Image.new("RGB", (320, 320), color).save(path, "WEBP")

    def run_generate(self, tmp, kinds, fail_extras=False):
        code = "CH-666-0001"
        story = dict(STORY, cover_image=f"https://example.com/images/{code}_cover.webp",
                     scene_images=f"https://example.com/images/{code}_scene.webp")
        story_path = Path(tmp) / "story.json"
        story_path.write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
        manifest = self.story_video.build_story_manifest(story)
        out = Path(tmp) / "out"
        out.mkdir()
        (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        local = Path(tmp) / "local"
        local.mkdir()
        for i, kind in enumerate(kinds):
            self.make_image(local / f"{code}_{kind}.webp", (30 * i + 20, 60, 90))

        def refuse(session, url, target):
            raise ValueError("HTTP 404")

        argv = ["x", str(out / "manifest.json"), "--story-json", str(story_path), "--output-dir", str(out),
                "--local-image-dir", str(local), "--execute"]
        env = {k: v for k, v in os.environ.items() if k != "AGNES_API_KEY"}
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(self.gsv, "download_image", refuse), contextlib.redirect_stdout(buf):
            rc = self.gsv.main()
        return rc, buf.getvalue(), out

    def test_three_distinct_stills_are_used_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, log, out = self.run_generate(tmp, ["cover", "scene", "scene_open", "scene_end"])
            self.assertEqual(rc, 0, log)
            self.assertIn("three distinct stills", log)
            for n in (1, 2, 3):
                self.assertTrue((out / f"scene-{n:02d}.webm").stat().st_size > 0)

    def test_falls_back_to_two_images_when_extras_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, log, out = self.run_generate(tmp, ["cover", "scene"])
            self.assertEqual(rc, 0, log)
            self.assertIn("Optional scene_open still not available", log)
            self.assertNotIn("three distinct stills", log)
            self.assertTrue((out / "scene-03.webm").is_file())


if __name__ == "__main__":
    unittest.main()
