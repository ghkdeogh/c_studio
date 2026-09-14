import json
from pathlib import Path
import tempfile
import unittest

import lesson_memory as memory
import production_assets as assets
import project_store


class LessonMemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = project_store.create(self.root, 'source', 'Source')
        self.target = project_store.create(self.root, 'target', '요리 쇼츠')
        self.pid = 'productions/video/target'
        project_store.upsert_cut(self.target, {'id': '01', 'name': '도입'})
        (self.target / 'BRIEF.md').write_text('# 요리 쇼츠\n음식과 얼굴, 손동작. 현재 사용자의 필수 지시.', encoding='utf-8')

    def add(self, ident='pace', folder=None, **kw):
        folder = folder or self.source
        item = {'id': ident, 'title': ident, 'observation': '사용자 검수', 'action': '불필요한 이동은 생략하고 음식으로 컷 전환',
                'context': '요리 쇼츠에 적용', 'scope': 'reusable', **kw}
        assets.upsert(folder, 'feedback', item)
        return next(r for r in memory.source_rows(self.root) if r['project_id'] == folder.relative_to(self.root).as_posix() and r['id'] == ident)

    def select(self, **kw):
        return memory.select(self.root, self.pid, **kw)

    def save(self, src, folder=None, **kw):
        folder = folder or self.target
        payload = {'ref': src['ref'], 'source_hash': src['source_hash'], 'revision': memory.load_plan(folder)['revision'],
                   'application': '01 도입의 이동 생략', 'cuts': ['01'], **kw}
        return memory.save_plan(self.root, folder.relative_to(self.root).as_posix(), payload)

    def review(self, src, folder=None, outcome='helpful'):
        folder = folder or self.target
        (folder / 'shots/review.mp4').write_bytes(b'registered QA video fixture')
        project_store.upsert_cut(folder, {'id': '01', 'name': '도입', 'video': 'shots/review.mp4'})
        return self.save(src, folder, stage='reviewed', outcome=outcome, evidence=['shots/review.mp4', 'renders.md'])

    def test_exact_duplicates_merge_without_modifying_originals(self):
        self.add('one')
        self.add('two', title='다른 제목')
        before = (self.source / 'feedback.json').read_bytes()
        r = self.select()
        self.assertEqual(len(r['items']), 1)
        self.assertEqual(len(r['items'][0]['refs']), 2)
        self.assertEqual(r['duplicate_count'], 1)
        self.assertEqual(before, (self.source / 'feedback.json').read_bytes())
        self.assertFalse((self.target / 'lesson-plan.json').exists())

    def test_conditions_and_opposing_stances_are_not_merged(self):
        self.add('face', action='발화 중 얼굴을 보여준다', learning={'topic': 'speaker', 'stance': 'face', 'keywords': ['요리']})
        self.add('voiceover', action='음식 화면에도 목소리를 이어간다', learning={'topic': 'speaker', 'stance': 'voiceover', 'keywords': ['요리']})
        self.assertEqual(self.select()['items'], [])
        all_rows = self.select(browse=True)['items']
        self.assertEqual(len(all_rows), 2)
        self.assertTrue(all('다른 방침' in ' '.join(x['warnings']) for x in all_rows))

    def test_other_genres_and_superseded_stances_do_not_create_false_conflicts(self):
        old = self.add('old', learning={'topic':'speaker','stance':'face','state':'active'})
        self.add('other', learning={'topic':'speaker','stance':'voiceover','keywords':['다큐']})
        self.assertEqual([r['id'] for r in self.select()['items']], ['old'])
        self.add('new', action='음식 위에 설명', learning={'topic':'speaker','stance':'voiceover','state':'active','supersedes':[old['ref']]})
        self.assertEqual([r['id'] for r in self.select()['items']], ['new'])

    def test_specific_legacy_conditions_need_review(self):
        self.add(action='60초를 유지하고 밀도를 늘린다', context='이번 글로벌 음식 소개 편')
        self.assertFalse(self.select()['items'])
        self.assertTrue(self.select(browse=True)['items'][0]['warnings'])

    def test_legacy_previs_and_running_do_not_leak_into_static_cooking(self):
        self.add('previs', action='카메라 참조 비교', context='Blender 프리비즈를 참고로 쓸 때')
        self.add('hair', action='달릴 때 머리카락 움직임', context='빠른 이동이나 바람이 있는 장면')
        self.assertFalse(self.select(stage='generation')['items'])
        self.assertEqual([r['id'] for r in self.select(stage='generation', query='Blender')['items']], ['previs'])
        self.assertEqual(len(self.select(stage='generation', browse=True)['items']), 2)

    def test_stage_model_and_exclusions(self):
        self.add(learning={'stages': ['generation'], 'models': ['model-a'], 'keywords': ['요리'], 'exclude_keywords': ['다큐']})
        self.assertFalse(self.select()['items'])
        self.assertFalse(self.select(stage='generation')['items'])
        self.assertEqual(len(self.select(stage='generation', model='model-a')['items']), 1)
        self.assertFalse(self.select(stage='generation', model='model-a', query='다큐')['items'])

    def test_current_private_retired_and_archived_are_excluded(self):
        self.add('current', self.target)
        self.add('private', scope='project')
        self.add('archived', status='archived')
        self.add('retired', learning={'state': 'retired'})
        self.assertEqual(self.select(browse=True)['source_count'], 0)

    def test_pagination_and_mandatory_context_separate(self):
        for i in range(14):
            self.add(str(i), action=f'음식 컷 {i}의 동작을 점검')
        one = self.select()
        two = self.select(offset=6)
        self.assertEqual(len(one['items']), 6)
        self.assertTrue(one['has_more'])
        self.assertFalse({r['ref'] for r in one['items']} & {r['ref'] for r in two['items']})
        self.assertEqual(one['constraints_source'], self.pid + '/BRIEF.md')

    def test_large_duplicate_pool_has_bounded_output(self):
        rows = [{'id':f'row-{i}','title':'같은 원칙','observation':'검수','action':'음식으로 전환','context':'요리','scope':'reusable','status':'open'} for i in range(2000)]
        assets.atomic(self.source/'feedback.json',{'schema_version':1,'revision':1,'items':rows})
        result = self.select()
        self.assertEqual(result['duplicate_count'],1999)
        self.assertEqual(result['items'][0]['ref_count'],2000)
        self.assertEqual(len(result['items'][0]['refs']),20)
        self.assertLess(len(json.dumps(result)),15000)

    def test_supersession_requires_applicable_replacement_and_detects_cycle(self):
        old = self.add('old')
        new = self.add('new', action='새 원칙', learning={'state': 'active', 'stages': ['generation'], 'supersedes': [old['ref']]})
        self.assertEqual([r['id'] for r in self.select()['items']], ['old'])
        self.assertEqual([r['id'] for r in self.select(stage='generation')['items']], ['new'])
        self.add('old', learning={'state': 'active', 'supersedes': [new['ref']]})
        self.assertFalse(self.select(stage='generation')['items'])
        self.assertTrue(all('순환' in ' '.join(r['warnings']) for r in self.select(stage='generation', browse=True)['items']))

    def test_curated_canonical_link_and_conditions(self):
        src = self.add('one', learning={'state': 'active', 'keywords': ['요리']})
        self.add('two', action='음식으로 바로 전환', learning={'state': 'active', 'keywords': ['요리'], 'canonical_ref': src['ref']})
        self.assertEqual(self.select()['duplicate_count'], 1)
        self.add('two', learning={'state': 'active', 'keywords': ['다큐'], 'canonical_ref': src['ref']})
        self.assertEqual(self.select(browse=True)['duplicate_count'], 0)

    def test_plan_revision_rollback_and_preservation(self):
        src = self.add()
        files = [self.source / 'feedback.json', self.target / 'project.json', self.target / 'BRIEF.md']
        before = {str(p): p.read_bytes() for p in files}
        first = self.save(src)
        with self.assertRaises(ValueError):
            self.save(src, revision=0)
        self.save(src, stage='applied', evidence=['shooting-script.md'])
        r = memory.save_plan(self.root, self.pid, {'operation': 'revert', 'ref': src['ref'], 'revision': 2, 'history_revision': 2})
        self.assertEqual(r['items'][0]['stage'], 'planned')
        self.assertEqual(r['revision'], 3)
        self.assertEqual(before, {str(p): p.read_bytes() for p in files})
        self.assertFalse((self.target / '.lesson-plan.lock').exists())

    def test_source_change_and_evidence_change_are_stale(self):
        src = self.add()
        self.save(src, stage='applied', evidence=['shooting-script.md'])
        (self.target / 'shooting-script.md').write_text('changed', encoding='utf-8')
        self.assertTrue(self.select()['plan']['items'][0]['stale'])
        self.add(action='새 내용')
        with self.assertRaises(ValueError):
            self.save(src)
        self.assertIn('원본 피드백', self.select()['plan']['items'][0]['stale'][0])

    def test_review_requires_registered_video_and_report(self):
        src = self.add()
        with self.assertRaises(ValueError):
            self.save(src, stage='reviewed', outcome='helpful', evidence=['shooting-script.md'])
        self.review(src)
        self.assertEqual(self.select()['items'][0]['outcomes']['helpful'], 1)
        self.assertFalse(self.select()['items'][0]['improvement_candidate'])

    def test_copies_do_not_inflate_independent_review_count(self):
        one = self.add('one')
        two = self.add('two')
        self.review(one)
        self.review(two)
        self.assertEqual(self.select()['items'][0]['outcomes']['helpful'], 1)
        other = project_store.create(self.root, 'other', 'Other')
        self.review(one, other)
        self.assertTrue(self.select()['items'][0]['improvement_candidate'])
        self.review(one, other, outcome='ineffective')
        group = self.select(browse=True)['items'][0]
        self.assertFalse(group['improvement_candidate'])
        self.assertTrue(group['warnings'])

    def test_path_escape_missing_cut_and_lock(self):
        src = self.add()
        for kwargs in [{'evidence': ['../../AGENTS.md']}, {'cuts': ['absent']}, {'ref': '../bad'}]:
            with self.assertRaises(ValueError):
                self.save(src, **kwargs)
        (self.target / '.lesson-plan.lock').write_text('another writer')
        with self.assertRaises(ValueError):
            self.save(src)
        self.assertEqual((self.target / '.lesson-plan.lock').read_text(), 'another writer')

    def test_curation_survives_existing_feedback_editor_updates(self):
        self.add(learning={'topic': 'tempo', 'state': 'active', 'keywords': ['요리']})
        assets.upsert(self.source, 'feedback', {'id': 'pace', 'title': '수정된 제목'})
        self.assertEqual(assets.load(self.source, 'feedback')['items'][0]['learning']['topic'], 'tempo')

    def test_rule_retirement_can_be_reverted_without_losing_feedback(self):
        self.add(learning={'state':'active','topic':'tempo'})
        before = assets.load(self.source, 'feedback')['items'][0]
        assets.upsert(self.source,'feedback',{'id':'pace','learning':{'state':'retired'}},1)
        self.assertFalse(self.select()['items'])
        restored = assets.restore_learning(self.source,'pace',2,2)
        row = restored['items'][0]
        self.assertEqual(row['learning'],before['learning'])
        for field in ('title','observation','action','context'):
            self.assertEqual(row[field],before[field])
        self.assertEqual(len(restored['learning_history']),3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
