import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from open_chat.support_context import (
    CONTENT_FILENAMES,
    build_support_context_prompt_section,
    load_support_context,
)


class _TempContentDir:
    def __init__(self, files: dict[str, str]):
        self._files = files
        self._tmp = None

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        path = Path(self._tmp.name)
        for name, content in self._files.items():
            (path / name).write_text(content, encoding="utf-8")
        return path

    def __exit__(self, *exc):
        self._tmp.cleanup()


class LoadSupportContextTests(SimpleTestCase):
    def test_loads_allow_listed_content_files_and_ignores_readme(self):
        with _TempContentDir(
            {
                "README.md": "do not load me",
                "handbook.md": "# Handbook\nBe kind.",
                "message_templates.md": "Hello {name}",
            }
        ) as directory:
            context = load_support_context(directory=directory)

        self.assertIn("Be kind.", context)
        self.assertIn("Hello {name}", context)
        self.assertNotIn("do not load me", context)
        self.assertIn("\n\n---\n\n", context)

    def test_returns_empty_for_missing_or_placeholder_only_directory(self):
        with _TempContentDir({}) as directory:
            self.assertEqual(load_support_context(directory=directory), "")

        with _TempContentDir(
            {
                "handbook.md": "<!-- TODO(1021): paste content -->",
                "message_templates.md": "<!-- TODO(1021): paste content -->",
            }
        ) as directory:
            self.assertEqual(load_support_context(directory=directory), "")

    def test_truncates_to_max_chars(self):
        with _TempContentDir({"handbook.md": "x" * 5000}) as directory:
            context = load_support_context(directory=directory, max_chars=100)

        self.assertEqual(len(context), 100)

    def test_directory_argument_overrides_setting(self):
        with _TempContentDir({"handbook.md": "from explicit dir"}) as explicit:
            with override_settings(OPEN_CHAT_SUPPORT_CONTEXT_DIR="/does/not/exist"):
                context = load_support_context(directory=explicit)

        self.assertEqual(context, "from explicit dir")

    def test_directory_setting_override_is_used(self):
        with _TempContentDir({"handbook.md": "from settings dir"}) as settings_dir:
            with override_settings(OPEN_CHAT_SUPPORT_CONTEXT_DIR=str(settings_dir)):
                context = load_support_context()

        self.assertEqual(context, "from settings dir")

    def test_committed_content_filenames_match_allow_list(self):
        self.assertEqual(CONTENT_FILENAMES, ("handbook.md", "message_templates.md"))


class BuildSupportContextPromptSectionTests(SimpleTestCase):
    def test_returns_empty_when_no_content(self):
        with _TempContentDir({"handbook.md": "<!-- TODO -->"}) as directory:
            self.assertEqual(build_support_context_prompt_section(directory=directory), "")

    def test_includes_label_and_content(self):
        with _TempContentDir({"handbook.md": "Escalate billing issues."}) as directory:
            section = build_support_context_prompt_section(directory=directory)

        self.assertTrue(section.startswith("Support handbook and reply templates"))
        self.assertIn("Escalate billing issues.", section)
