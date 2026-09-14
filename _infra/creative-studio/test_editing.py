import unittest, tempfile, json, subprocess, time, hashlib, shutil
from pathlib import Path
import server, media_engine
from project_store import create, read, save, validate

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class EditingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();server.ROOT=self.root
        self.p=create(self.root,'frame-test','Frame test');self.pid='productions/video/frame-test'
        for cid,fps,audio in [('01',24,True),('02',30,False)]:
            folder=self.p/'shots'/cid;folder.mkdir();path=folder/'result.mp4'
            args=['ffmpeg','-v','error','-f','lavfi','-i',f'testsrc2=size=160x120:rate={fps}:duration=1']
            if audio:args+=['-f','lavfi','-i','sine=frequency=440:duration=1','-c:a','aac']
            subprocess.run(args+['-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
        d=read(self.p/'project.json');d['cuts']=[dict(id=c,name=c,status='review',video=f'shots/{c}/result.mp4') for c in ['01','02']];save(self.p/'project.json',d)
    def tearDown(self):self.tmp.cleanup()
    def trim(self,cid,a,b,revision=0):
        info=media_engine.probe(self.p/f'shots/{cid}/result.mp4')
        return server.save_trim(dict(project=self.pid,cut=cid,source_sha256=info['sha256'],in_frame=a,out_frame=b,revision=revision))
    def test_boundaries_stale_source_concurrency_preservation(self):
        p=self.p/'shots/01/result.mp4';info=media_engine.probe(p)
        self.assertEqual(info['count'],24);self.assertAlmostEqual(info['frames'][6],.25)
        server.save_state(self.p,{'schema':1,'cuts':{'01':{'note':'Keep me','versions':[{'id':'x','path':'shots/01/ref.png'}],'selected':'x'}}})
        (p.parent/'ref.png').write_bytes(b'image')
        self.trim('01',6,18)
        self.assertEqual(server.state(self.p)['cuts']['01']['note'],'Keep me')
        with self.assertRaises(ValueError):self.trim('01',0,24,0)
        with self.assertRaises(ValueError):self.trim('01',6,6,1)
        with self.assertRaises(ValueError):self.trim('01',-1,25,1)
        with self.assertRaises(ValueError):media_engine.valid_trim(info,dict(source_sha256='wrong',in_frame=0,out_frame=24))
        c=server.catalog(self.pid)['cuts'][0];self.assertFalse(c['trim_stale'])
        p.touch();self.assertTrue(server.catalog(self.pid)['cuts'][0]['trim_stale'])
        self.assertEqual(media_engine.probe(p)['sha256'],info['sha256'])
    def test_export_same_order_mixed_fps_silent_and_reload(self):
        originals={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.p.glob('shots/*/result.mp4')}
        self.trim('01',6,18);self.trim('02',0,15)
        server.save_timeline(dict(project=self.pid,cuts=['02','01'],revision=0))
        with self.assertRaises(ValueError):server.save_timeline(dict(project=self.pid,cuts=['01','01'],revision=1))
        result=server.export_project({'project':self.pid});path=self.p/'exports'/result['id']/'job.json'
        deadline=time.time()+45
        while time.time()<deadline:
            job=read(path)
            if job['status'] in ('complete','error'):break
            time.sleep(.05)
        self.assertEqual(job['status'],'complete',job.get('error'))
        self.assertEqual([x['cut'] for x in job['outputs']['edited']['timeline']],['02','01'])
        self.assertAlmostEqual(job['outputs']['raw']['duration'],2,delta=.04)
        self.assertAlmostEqual(job['outputs']['edited']['duration'],1,delta=.04)
        self.assertEqual(job['outputs']['edited']['frames'],30)
        self.assertEqual(job['outputs']['raw']['frames'],60)
        self.assertTrue(media_engine.probe(self.p/job['outputs']['edited']['path'])['audio'])
        self.assertEqual(server.catalog(self.pid)['jobs'][0]['status'],'complete')
        self.assertEqual(originals,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.p.glob('shots/*/result.mp4')})
        self.assertEqual(validate(self.p,read(self.p/'project.json')),[])
    def test_export_rejects_missing_selection_before_creating_output(self):
        server.save_timeline(dict(project=self.pid,cuts=['01'],revision=0))
        with self.assertRaises(ValueError):server.export_project({'project':self.pid})
        self.assertFalse(list((self.p/'exports').glob('studio-*')))

if __name__=='__main__':unittest.main()
