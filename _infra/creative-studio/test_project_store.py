import unittest,tempfile,json
from pathlib import Path
from project_store import create,validate,read,save,adopt,upsert_cut
import server

class ProjectContractTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
    def tearDown(self):self.tmp.cleanup()
    def test_new_project_and_planned_cut(self):
        p=create(self.root,'test-film','새 작품');d=read(p/'project.json')
        self.assertEqual(validate(p,d),[])
        d['cuts']=[{'id':'01','name':'기획 중','status':'planned','video':None,'duration':None}];save(p/'project.json',d)
        server.ROOT=self.root;c=server.catalog('productions/video/test-film')
        self.assertEqual(c['name'],'새 작품');self.assertIsNone(c['cuts'][0]['video']);self.assertEqual(c['cuts'][0]['status'],'planned')
        self.assertTrue((p/'AGENTS.md').exists())
        with self.assertRaises(FileExistsError):create(self.root,'test-film','overwrite')
    def test_invalid_paths_and_duplicate_cut(self):
        p=create(self.root,'test-film','Test');d=read(p/'project.json')
        d['cuts']=[{'id':'01','name':'A','status':'review','video':'../../../outside.mp4'},{'id':'01','name':'B','status':'planned'}]
        errors=validate(p,d);self.assertTrue(any('escapes' in e for e in errors));self.assertTrue(any('duplicate' in e for e in errors))
        with self.assertRaises(ValueError):create(self.root,'../outside','No')
    def test_conversation_cut_registration_is_atomic_and_preserves_user_state(self):
        p=create(self.root,'test-film','Test');(p/'assets/start.png').write_bytes(b'image')
        user_state=p/'.studio/state.json';user_state.write_text('{"cuts":{"01":{"note":"keep"}}}')
        upsert_cut(p,dict(id='01',name='First',planned_start_image='assets/start.png'))
        upsert_cut(p,dict(id='01',name='Renamed'))
        self.assertEqual(len(read(p/'project.json')['cuts']),1)
        self.assertEqual(read(p/'project.json')['cuts'][0]['planned_start_image'],'assets/start.png')
        before=(p/'project.json').read_bytes()
        with self.assertRaises(ValueError):upsert_cut(p,dict(id='01',planned_end_image='../missing.png'))
        self.assertEqual((p/'project.json').read_bytes(),before)
        self.assertIn('keep',user_state.read_text())
    def test_legacy_adoption_preserves_files(self):
        p=self.root/'legacy';d=p/'shots/take-01';d.mkdir(parents=True);(p/'BRIEF.md').write_text('original');(d/'result.mp4').write_bytes(b'media')
        adopt(p);self.assertEqual(read(p/'project.json')['cuts'][0]['video'],'shots/take-01/result.mp4')
        self.assertEqual((d/'result.mp4').read_bytes(),b'media')
        with self.assertRaises(ValueError):adopt(p)

if __name__=='__main__':unittest.main()
