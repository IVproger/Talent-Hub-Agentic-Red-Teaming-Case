from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agentic_redteam.attacker.idea_sources import load_idea_files
from agentic_redteam.errors import PipelineConfigurationError


class IdeaSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def file(self, name, content):
        path = self.root / name
        path.write_text(content, encoding='utf-8')
        return str(path)

    def test_text_and_markdown_preserve_structure_and_order(self):
        paths = [self.file('one.txt', '\ufeffПервая идея\n'),
                 self.file('two.MD', '# Проверка\n\n- Сессия 1\n- Сессия 2\n')]
        self.assertEqual(load_idea_files(paths), [
            'Первая идея', '# Проверка\n\n- Сессия 1\n- Сессия 2'])

    def test_yaml_list_and_mapping(self):
        paths = [self.file('one.yaml', '- "Первая"\n- |\n  Вторая\n  С пояснением\n'),
                 self.file('two.yml', 'ideas:\n  - Третья\n')]
        self.assertEqual(load_idea_files(paths), ['Первая', 'Вторая\nС пояснением', 'Третья'])

    def test_invalid_sources_are_configuration_errors(self):
        for name, content in [('empty.txt', ' \n'), ('empty.yaml', '[]'),
                              ('bad.yaml', 'ideas: текст'), ('num.yaml', '- 42'),
                              ('null.yaml', '- null'), ('blank.yaml', '- " "'),
                              ('extra.yaml', 'ideas: [текст]\nother: x'),
                              ('syntax.yaml', '['), ('bad.json', '[]'),
                              ('large.txt', 'a' * 65537)]:
            with self.subTest(name=name):
                with self.assertRaisesRegex(PipelineConfigurationError, '--ideas-file'):
                    load_idea_files([self.file(name, content)])
        for path in [self.root / 'missing.txt', self.root]:
            with self.assertRaises(PipelineConfigurationError):
                load_idea_files([str(path)])

    def test_invalid_utf8(self):
        path = self.root / 'bad.txt'
        path.write_bytes(b'\xff')
        with self.assertRaisesRegex(PipelineConfigurationError, '--ideas-file'):
            load_idea_files([str(path)])
