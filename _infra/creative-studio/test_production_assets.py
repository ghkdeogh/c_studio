import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import production_assets as assets
import project_store
import server


class ProductionAssetsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p = project_store.create(self.root, 'first', 'First')
        self.other = project_store.create(self.root, 'second', 'Second')
        self.prior_root = server.ROOT
        server.ROOT = self.root
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.ROOT = self.prior_root
        self.temp.cleanup()

    def request(self, route, body=None, token=True):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Studio-Token'] = server.TOKEN
        req = urllib.request.Request(self.base+route, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def test_character_image_upload_revision_and_preservation(self):
        old_project = (self.p/'project.json').read_bytes()
        user_state = self.p/'.studio/state.json'
        user_state.write_text('{"cuts":{"01":{"note":"keep","selected":"keep"}}}')
        old_state = user_state.read_bytes()
        row = {'id': 'lead', 'name': 'Lead', 'description': '<script>not executable</script>', 'images': []}
        self.request('/api/characters', {'project':'productions/video/first', 'item':row, 'revision':0})
        self.request('/api/characters', {'project':'productions/video/first', 'action':'upload', 'id':'lead', 'revision':1, 'name':'sheet.png', 'bytes':base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode(), 'kind':'sheet'})
        current = assets.load(self.p, 'characters')
        self.assertEqual(current['revision'], 2)
        image = current['items'][0]['images'][0]
        self.assertTrue((self.p/image['path']).is_file())
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/characters', {'project':'productions/video/first','item':row,'revision':1})
        self.assertEqual(assets.load(self.p,'characters')['revision'], 2)
        self.assertEqual(old_project, (self.p/'project.json').read_bytes())
        self.assertEqual(old_state, user_state.read_bytes())
        catalog = self.request('/api/project?id=productions/video/first')
        self.assertIn('/media?', catalog['characters']['items'][0]['images'][0]['url'])

    def test_reuse_excludes_private_and_archived_and_is_not_copied(self):
        for ident,scope,status in [('one','reusable','open'),('two','project','open'),('three','reusable','archived')]:
            assets.upsert(self.p,'feedback',{'id':ident,'title':ident,'observation':'observed','action':'next','scope':scope,'status':status,'tags':['검수']})
        result = self.request('/api/project?id=productions/video/second')
        self.assertEqual([x['id'] for x in result['lessons']], ['one'])
        self.assertEqual(result['lessons'][0]['project_name'], 'First')
        self.assertEqual(result['feedback']['items'], [])
        self.assertEqual(assets.load(self.other,'feedback')['items'], [])

    def test_validation_auth_and_project_isolation(self):
        row={'id':'lead','name':'Lead','images':[{'path':'../outside.png'}]}
        with self.assertRaises(ValueError): assets.upsert(self.p,'characters',row)
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/characters',{'project':'productions/video/first','item':{'id':'lead','name':'Lead'},'revision':0},token=False)
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/feedback',{'project':'productions/video/first','item':{'id':'note','title':'Missing action'},'revision':0})
        self.assertEqual(assets.load(self.p,'feedback')['revision'],0)
        self.assertEqual(assets.load(self.other,'characters')['items'],[])

    def test_new_and_legacy_projects_have_empty_views(self):
        self.assertTrue((self.p/'characters.json').exists())
        (self.other/'characters.json').unlink()
        (self.other/'feedback.json').unlink()
        result=self.request('/api/project?id=productions/video/second')
        self.assertEqual(result['characters']['items'],[])
        self.assertEqual(result['feedback']['items'],[])

    def test_lesson_selection_and_application_api(self):
        assets.upsert(self.p, 'feedback', {'id':'camera','title':'카메라 경로','observation':'검수','action':'카메라를 천천히 이동','scope':'reusable'})
        selected = self.request('/api/lessons?project=productions/video/second')
        row = selected['items'][0]
        self.assertEqual(row['project_name'], 'First')
        payload = {'project':'productions/video/second','ref':row['ref'],'source_hash':row['source_hash'],'revision':0,'stage':'planned','application':'공간 공개 장면에 적용','cuts':[]}
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/lesson-plan',payload,token=False)
        saved = self.request('/api/lesson-plan',payload)
        self.assertEqual(saved['revision'],1)
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/lesson-plan',payload)
        catalog = self.request('/api/project?id=productions/video/second')
        self.assertEqual(catalog['lesson_selection']['plan']['items'][0]['stage'],'planned')
        self.assertEqual(assets.load(self.other,'feedback')['items'],[])


class ProductionAssetsCLITest(unittest.TestCase):
    def test_lessons_outputs_utf8_under_legacy_windows_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = project_store.create(root, 'source', 'Source \u2014 film')
            title = 'Camera \u2013 timing \U0001f3ac'
            assets.upsert(folder, 'feedback', {
                'id': 'camera', 'title': title, 'observation': 'Observed',
                'action': 'Review timing', 'scope': 'reusable',
            })
            before = (folder / 'feedback.json').read_bytes()
            result = subprocess.run(
                [sys.executable, '-B', str(Path(assets.__file__)), 'lessons', str(root), '--raw'],
                env={**os.environ, 'PYTHONIOENCODING': 'cp949', 'PYTHONUTF8': '0'},
                capture_output=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
            rows = json.loads(result.stdout.decode('utf-8'))
            self.assertEqual(rows[0]['title'], title)
            self.assertEqual(rows[0]['project_name'], 'Source \u2014 film')
            self.assertEqual((folder / 'feedback.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
