import unittest,tempfile,json,threading,urllib.request,urllib.error,base64
from pathlib import Path
from unittest.mock import patch
import server

class StudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);server.ROOT=self.root
        self.p=self.root/'productions/video/demo';self.p.mkdir(parents=True);(self.p/'BRIEF.md').write_text('story')
        self.d=self.p/'shots/full-pass-h3-v1';self.d.mkdir(parents=True)
        (self.d/'result.mp4').write_bytes(b'0123456789')
        (self.d/'assembly-report.json').write_text(json.dumps({'timeline':[{'id':'01','name':'Entry','local_path':'shots/full-pass-h3-v1/result.mp4','duration':5,'start':0}]}))
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.base=f'http://127.0.0.1:{self.http.server_port}'
    def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        h=headers or {}
        if body is not None:h.update({'X-Studio-Token':server.TOKEN,'Content-Type':'application/json'})
        return urllib.request.urlopen(urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=h))
    def edit(self,**kw):return json.load(self.request('/api/edit',dict(project='productions/video/demo',cut='01',**kw)))
    def test_import_upload_restore_and_preservation(self):
        self.assertEqual(len(json.load(self.request('/api/project?id=productions/video/demo'))['cuts']),1)
        self.edit(action='upload',name='demo.png',bytes=base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode())
        first=server.state(self.p)['cuts']['01']['selected']
        self.edit(action='upload',name='second.png',bytes=base64.b64encode(b'\x89PNG\r\n\x1a\nsecond').decode())
        self.edit(action='select',version=first);self.edit(action='note',note='2.5초 확인')
        st=server.state(self.p)['cuts']['01'];self.assertEqual(st['selected'],first);self.assertEqual(len(st['versions']),2);self.assertEqual(st['note'],'2.5초 확인')
        self.assertEqual((self.d/'result.mp4').read_bytes(),b'0123456789');self.assertEqual((self.p/'BRIEF.md').read_text(),'story')
    def test_range_and_traversal(self):
        path='/media?project=productions/video/demo&path=shots/full-pass-h3-v1/result.mp4'
        with self.request(path,headers={'Range':'bytes=2-5'}) as r:self.assertEqual(r.status,206);self.assertEqual(r.read(),b'2345')
        with self.assertRaises(urllib.error.HTTPError):self.request('/media?project=productions/video/demo&path=../../../../outside.md')
        with self.assertRaises(urllib.error.HTTPError):self.request(path,headers={'Range':'bytes=20-30'})
    def test_open_output_folder_is_scoped_and_authenticated(self):
        rel='shots/full-pass-h3-v1/result.mp4'
        (self.p/'project.json').write_text(json.dumps({'full_video':rel}))
        body={'project':'productions/video/demo','path':rel}
        with patch.object(server.os,'startfile',create=True) as launch:
            self.assertTrue(json.load(self.request('/api/open-output-folder',body))['ok'])
            launch.assert_called_once_with(str(self.d.resolve()))
            for path in ['../../../../outside.mp4','BRIEF.md']:
                with self.assertRaises(urllib.error.HTTPError):self.request('/api/open-output-folder',dict(body,path=path))
            self.assertEqual(launch.call_count,1)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(urllib.request.Request(self.base+'/api/open-output-folder',data=json.dumps(body).encode()))
            self.assertEqual(launch.call_count,1)
    def test_write_token_and_invalid_image(self):
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(self.base+'/api/edit',data=b'{}'))
        with self.assertRaises(urllib.error.HTTPError):self.edit(action='upload',name='x.jpg',bytes=base64.b64encode(b'not image').decode())
        self.assertFalse((self.p/'.studio/state.json').exists())
    def test_role_review_endpoints(self):
        pid='productions/video/demo';q='/api/role-review?project='+pid
        v=json.load(self.request(q));self.assertEqual(v['revision'],0);self.assertTrue(v['items']);self.assertTrue(all(i['status']=='pending' for i in v['items']))
        self.assertEqual(json.load(self.request('/api/project?id='+pid))['role_review_revision'],0)
        item=v['items'][0]['id'];body={'project':pid,'item':item,'status':'pass','note':' 확인 ','by':'editor','revision':0}
        with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(urllib.request.Request(self.base+'/api/role-review',data=json.dumps(body).encode()))
        self.assertEqual(ctx.exception.code,403);self.assertFalse((self.p/'role-review.json').exists())
        v=json.load(self.request('/api/role-review',body));row=next(i for i in v['items'] if i['id']==item)
        self.assertEqual((v['revision'],row['status'],row['note'],row['by']),(1,'pass','확인','editor'))
        self.assertEqual(json.load(self.request('/api/project?id='+pid))['role_review_revision'],1)
        for bad in [dict(body,revision=0),dict(body,revision=1,status='done'),dict(body,revision=1,item='nope'),dict(body,revision='1'),dict(body,revision=1,note=['x']),{k:x for k,x in body.items() if k!='revision'},dict(body,revision=1,project='../outside')]:
            with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/role-review',bad)
            self.assertEqual(ctx.exception.code,400);self.assertIn('error',json.load(ctx.exception))
        self.assertEqual(json.loads((self.p/'role-review.json').read_text(encoding='utf-8'))['revision'],1)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/role-review?project=../outside')
        with self.request('/roles.js') as r:self.assertIn('renderRoleReview',r.read().decode('utf-8'))

if __name__=='__main__':unittest.main()
