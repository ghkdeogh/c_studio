"""Regression checks: no network, packages, generation or subprocesses."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('router', Path(__file__).resolve().parents[1] / 'router.py')
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((router.ROOT / 'docs/agent/routes.json').read_text(encoding='utf-8'))

    def test_structure(self):
        router.validate(self.config)

    def test_seven_representative_requests(self):
        for tag in sorted(router.IDS):
            with self.subTest(tag=tag):
                result = router.select(self.config, [tag], 'productions/_template' if tag == 'resume-project' else None)
                self.assertEqual(result['status'], 'ok')
                self.assertEqual(result['routes'], [tag])
                self.assertTrue(result['documents'])
                self.assertLess(result['total_bytes'], 81920)

    def test_resume_order_and_scope(self):
        result = router.select(self.config, ['resume-project'], 'productions/_template/BRIEF.md')
        self.assertEqual([d['path'] for d in result['documents']],
                         ['productions/_template/생성상태.md', 'productions/_template/BRIEF.md'])
        self.assertEqual(router.select(self.config, ['resume-project'])['status'], 'project-path-required')
        for target in ['productions', 'docs/agent', 'productions/missing']:
            with self.assertRaises(ValueError):
                router.select(self.config, ['resume-project'], target)

    def test_unsafe_paths(self):
        for value in ['../outside', '/absolute', 'C:/outside', 'docs\\agent', 'docs/../AGENTS.md', 'docs//agent', './AGENTS.md', 'docs/']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                router.safe_path(value)

    def test_resolved_link_escape(self):
        # Simulate Windows junction resolution without creating system links.
        original = Path.resolve
        root = router.ROOT
        def resolve(path, *args, **kwargs):
            if path == root / 'linked':
                return root.parent / 'outside'
            return original(path, *args, **kwargs)
        with patch.object(Path, 'resolve', resolve), self.assertRaises(ValueError):
            router.safe_path('linked')

    def test_bad_config(self):
        variants = []
        c = copy.deepcopy(self.config); c['unexpected'] = True; variants.append(c)
        c = copy.deepcopy(self.config); c['routes'].append(c['routes'][0]); variants.append(c)
        c = copy.deepcopy(self.config); c['routes'][0]['read_order'] = ['CONTEXT.md']; variants.append(c)
        c = copy.deepcopy(self.config); c['routes'][0]['read_order'] = ['missing.md']; variants.append(c)
        c = copy.deepcopy(self.config); c['routes'][0]['read_order'] = ['../outside.md']; variants.append(c)
        c = copy.deepcopy(self.config); c['routes'][0]['match'] = {}; variants.append(c)
        c = copy.deepcopy(self.config); c['representative_tags']['repo-docs'] = 'story-planning'; variants.append(c)
        c = copy.deepcopy(self.config); c['routes'][5]['conditional_docs'][0]['nearest'].reverse(); variants.append(c)
        for index, config in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                router.validate(config)

    def test_deduplication(self):
        self.config['routes'][1]['read_order'].append('docs/agent/README.md')
        result = router.select(self.config, ['repo-docs', 'story-planning'])
        paths = [d['path'] for d in result['documents']]
        expected = list(dict.fromkeys(self.config['routes'][0]['read_order'] + self.config['routes'][1]['read_order']))
        self.assertEqual(paths, expected)
        self.assertEqual(paths.count('docs/agent/README.md'), 1)

    def test_unknown_intent(self):
        result = router.select(self.config, ['unknown'])
        self.assertEqual(result['status'], 'clarify-intent')
        self.assertEqual(result['documents'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
