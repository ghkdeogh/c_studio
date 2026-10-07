import unittest,tempfile,json
from pathlib import Path
import role_review

class RoleReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)/'productions/video/demo';self.p.mkdir(parents=True)
        self.spec=role_review.checklist();self.first=self.spec['items'][0]['id']
    def tearDown(self):self.tmp.cleanup()
    def test_view_defaults_to_pending_without_creating_state(self):
        v=role_review.view(self.p)
        self.assertEqual(v['revision'],0);self.assertEqual(len(v['items']),len(self.spec['items']))
        self.assertEqual([s['id'] for s in v['stages']],[s['id'] for s in self.spec['stages']])
        self.assertTrue(all(i['status']=='pending' and i['note']=='' and i['at'] is None for i in v['items']))
        self.assertTrue({i['role'] for i in v['items']}<={r['id'] for r in v['roles']})
        self.assertFalse((self.p/'role-review.json').exists())
    def test_set_pass_and_fail_persist_with_revision(self):
        v=role_review.set_check(self.p,self.first,'pass','확인함','editor',0)
        self.assertEqual(v['revision'],1)
        row=next(i for i in v['items'] if i['id']==self.first)
        self.assertEqual((row['status'],row['note'],row['by']),('pass','확인함','editor'));self.assertIsNotNone(row['at'])
        v=role_review.set_check(self.p,'rev-anatomy','fail','3.25초 손가락 6개','',1)
        self.assertEqual(v['revision'],2)
        saved=json.loads((self.p/'role-review.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['schema_version'],1);self.assertEqual(saved['revision'],2)
        self.assertEqual(saved['checks']['rev-anatomy']['status'],'fail');self.assertEqual(saved['checks'][self.first]['note'],'확인함')
        self.assertEqual([i['id'] for i in role_review.gate(self.p) if i['id']=='rev-anatomy'],['rev-anatomy'])
        self.assertFalse(list(self.p.glob('*.tmp')))
    def test_invalid_item_status_and_note_are_rejected_without_writing(self):
        for args in [('no-such-item','pass'),(self.first,'done'),(self.first,'')]:
            with self.assertRaises(role_review.ReviewError):role_review.set_check(self.p,*args,revision=0)
        with self.assertRaises(role_review.ReviewError):role_review.set_check(self.p,self.first,'pass','x'*2001,revision=0)
        self.assertFalse((self.p/'role-review.json').exists())
    def test_revision_conflict_keeps_existing_state(self):
        role_review.set_check(self.p,self.first,'pass',revision=0)
        before=(self.p/'role-review.json').read_bytes()
        with self.assertRaises(role_review.ReviewError) as ctx:role_review.set_check(self.p,self.first,'fail',revision=0)
        self.assertIn('먼저 바뀌었습니다',str(ctx.exception))
        self.assertEqual((self.p/'role-review.json').read_bytes(),before)
        self.assertEqual(role_review.set_check(self.p,self.first,'na',revision=1)['revision'],2)
    def test_malformed_state_is_reported(self):
        (self.p/'role-review.json').write_text('{"schema_version":2,"checks":{}}',encoding='utf-8')
        with self.assertRaises(role_review.ReviewError):role_review.view(self.p)

if __name__=='__main__':unittest.main()
