import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

import production_assets as assets
import project_store
import server
import youtube_analytics as yt
import youtube_auth as auth

VID = 'j9Sb9LsXcrU'
CHANNEL = 'UC' + 'a' * 22


class YoutubeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p = project_store.create(self.root, 'one', 'One')
        self.q = project_store.create(self.root, 'two', 'Two')
        self.previous = server.ROOT
        server.ROOT = self.root
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'
        self.vault_patch = patch.object(auth, 'vault_path', return_value=self.root/'private'/'auth.bin')
        self.vault_patch.start()
        auth.PENDING.clear()

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join()
        server.ROOT = self.previous
        self.vault_patch.stop();self.temp.cleanup()

    def request(self, route, body=None, token=True):
        headers = {'Content-Type':'application/json'}
        if token: headers['X-Studio-Token'] = server.TOKEN
        request = urllib.request.Request(self.base+route, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(request) as response: return json.load(response)

    def connect_video(self):
        return yt.link(self.p, {'video_id':VID, 'channel_id':CHANNEL, 'title':'Test', 'published_date':'2026-09-11'}, 0)

    def snapshot(self):
        return {'video_id':VID, 'start_date':'2026-09-11', 'end_date':'2026-09-12',
                'as_of':'2026-09-12T11:00:00+09:00',
                'metrics':{'views':695, 'engagedViews':268, 'averageViewPercentage':92.8,
                           'averageViewDuration':72, 'subscribersNet':4, 'stayedToWatch':43, 'swipedAway':57}}

    def test_urls_publication_and_project_boundaries(self):
        for value in [VID, 'https://youtu.be/'+VID, 'https://www.youtube.com/shorts/'+VID+'?x=1', 'https://youtube.com/watch?v='+VID]:
            self.assertEqual(yt.video_id(value), VID)
        for value in ['https://youtube.com.evil/watch?v='+VID, 'http://youtube.com/watch?v='+VID, 'https://evil.test/'+VID, 'javascript:alert(1)']:
            with self.assertRaises(ValueError):yt.video_id(value)
        out=self.p/'exports'/'v001';out.mkdir(parents=True)
        (out/'edited.mp4').write_bytes(b'test')
        (out/'youtube-publication.json').write_text(json.dumps({'status':'published','video_id':VID,'date':'2026-09-11','source':'exports/v001/edited.mp4'}))
        found=yt.discoveries(self.p)
        self.assertEqual(found[0]['source'],'exports/v001/edited.mp4')
        self.assertFalse((self.p/yt.FILE).exists())
        for source in ['../outside.mp4', 'C:/outside.mp4']:
            with self.assertRaises(ValueError):yt.link(self.p,{'video_id':VID,'source':source},0)

    def test_snapshot_history_nulls_idempotency_concurrency_and_preservation(self):
        self.connect_video()
        original=(self.p/'project.json').read_bytes()
        state=self.p/'.studio/state.json';state.write_text('{"cuts":{"01":{"note":"keep"}}}')
        prior=state.read_bytes()
        one=yt.add_snapshot(self.p,self.snapshot(),1)
        self.assertIsNone(one['snapshots'][0]['metrics']['shares'])
        self.assertEqual(one['snapshots'][0]['metrics']['stayedToWatch'],43)
        two=yt.add_snapshot(self.p,self.snapshot(),2)
        self.assertEqual(len(two['snapshots']),1)
        later={**self.snapshot(),'as_of':'2026-09-13T11:00:00+09:00','metrics':{'views':0}}
        three=yt.add_snapshot(self.p,later,2)
        self.assertEqual([s['metrics']['views'] for s in three['snapshots']],[695,0])
        with self.assertRaises(ValueError):yt.add_snapshot(self.p,later,1)
        self.assertEqual(state.read_bytes(),prior)
        self.assertEqual((self.p/'project.json').read_bytes(),original)
        self.assertFalse((self.q/yt.FILE).exists())

    def test_invalid_metrics_never_write_and_manual_cannot_claim_api(self):
        self.connect_video()
        for metrics in [{'views':float('nan')},{'views':True},{'views':-1},{'views':1.5},{'stayedToWatch':101},{'views':None},{'madeUp':1},{'stayedToWatch':43,'swipedAway':50}]:
            with self.assertRaises(ValueError):yt.add_snapshot(self.p,{**self.snapshot(),'metrics':metrics},1)
        with self.assertRaises(ValueError):yt.add_snapshot(self.p,{**self.snapshot(),'as_of':'2026-09-12T01:00:00'},1)
        with self.assertRaises(ValueError):yt.add_snapshot(self.p,{**self.snapshot(),'start_date':'2026-09-15'},1)
        self.assertEqual(yt.load(self.p)['revision'],1)
        result=self.request('/api/youtube/snapshot',{'project':'productions/video/one','revision':1,'item':{**self.snapshot(),'source':'youtube_api','retention':[{'fake':1}]}})
        self.assertEqual(result['snapshots'][0]['source'],'studio_manual')
        self.assertEqual(result['snapshots'][0]['retention'],[])
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/youtube/link',{'project':'productions/video/two','revision':0,'item':{'video_id':VID}},token=False)

    def test_retrospective_requires_actual_evidence_and_preserves_reuse(self):
        self.connect_video();doc=yt.add_snapshot(self.p,self.snapshot(),1)
        draft=yt.draft(self.p,VID,doc['snapshots'][0]['id'])
        self.assertEqual(assets.load(self.p,'feedback')['items'],[])
        draft.update(id='youtube-review',scope='reusable')
        with self.assertRaises(ValueError):assets.upsert(self.p,'feedback',draft,0)
        draft['retrospective'].update(hypothesis='도입부 가설',experiment='첫 화면 변경',success_measure='같은 기간 비교')
        saved=assets.upsert(self.p,'feedback',draft,0)
        self.assertEqual(saved['items'][0]['retrospective']['confidence'],'hypothesis')
        with self.assertRaises(ValueError):assets.upsert(self.q,'feedback',draft,0)
        catalog=self.request('/api/project?id=productions/video/two')
        self.assertEqual(catalog['lessons'][0]['retrospective']['snapshot_id'],doc['snapshots'][0]['id'])
        self.assertEqual(catalog['feedback']['items'],[])
        with self.assertRaises(ValueError):assets.upsert(self.p,'feedback',dict(draft,retrospective={**draft['retrospective'],'scene_seconds':float('inf')}),1)

    def test_api_summary_partial_failure_and_ownership(self):
        self.connect_video()
        def mock(endpoint, params=None, bearer=None, **kwargs):
            if endpoint.endswith('/videos'):return {'items':[{'snippet':{'channelId':CHANNEL}}]}
            self.assertEqual(params['filters'],'video=='+VID)
            self.assertEqual(params['ids'],'channel=='+CHANNEL)
            if params.get('dimensions')=='elapsedVideoTimeRatio':raise auth.GoogleError('아직 제공 안됨')
            if params.get('dimensions')=='insightTrafficSourceType':return {'columnHeaders':[{'name':'insightTrafficSourceType'},{'name':'views'}],'rows':[['SHORTS',600]]}
            if params.get('dimensions')=='day':return {'columnHeaders':[{'name':'day'},{'name':'views'}],'rows':[['2026-09-11',695]]}
            return {'columnHeaders':[{'name':k} for k in ['views','engagedViews','subscribersGained','subscribersLost']], 'rows':[[695,268,5,1]]}
        with patch.object(auth,'access',return_value=('not-a-token',{'id':CHANNEL})),patch.object(auth,'request_json',side_effect=mock):
            snap=yt.collect(self.p,VID,'2026-09-11','2026-09-12')
        self.assertEqual(snap['metrics']['subscribersNet'],4)
        self.assertEqual(snap['available_through'],'2026-09-11')
        self.assertEqual(snap['retention'],[])
        self.assertTrue(any('아직 제공 안됨' in w for w in snap['warnings']))
        self.assertNotIn('stayedToWatch',snap['metrics'])
        with patch.object(auth,'access',return_value=('not-a-token',{'id':'different-channel'})),patch.object(auth,'request_json',return_value={'items':[{'snippet':{'channelId':CHANNEL}}]}):
            with self.assertRaisesRegex(ValueError,'소유 채널'):yt.collect(self.p,VID,'2026-09-11','2026-09-12')

    def test_empty_api_results_are_not_zero(self):
        self.connect_video()
        with patch.object(auth,'access',return_value=('not-a-token',{'id':CHANNEL})),patch.object(auth,'request_json',side_effect=[{'items':[{'snippet':{'channelId':CHANNEL}}]}, {'rows':[]}]):
            with self.assertRaisesRegex(ValueError,'0으로 저장하지'):yt.collect(self.p,VID,'2026-09-11','2026-09-12')
        self.assertEqual(yt.load(self.p)['snapshots'],[])

    def test_snapshot_keeps_source_and_changed_original_disables_playback(self):
        source=self.p/'exports'/'first.mp4';source.write_bytes(b'original')
        yt.link(self.p,{'video_id':VID,'source':'exports/first.mp4'},0)
        doc=yt.add_snapshot(self.p,self.snapshot(),1)
        self.assertEqual(doc['snapshots'][0]['source_file'],'exports/first.mp4')
        catalog=server.catalog('productions/video/one')
        self.assertTrue(catalog['youtube']['snapshots'][0]['source_file_url'])
        source.write_bytes(b'changed original')
        catalog=server.catalog('productions/video/one')
        self.assertIsNone(catalog['youtube']['snapshots'][0]['source_file_url'])
        self.assertTrue(catalog['youtube']['snapshots'][0]['source_warning'])
        self.assertEqual(yt.load(self.p)['snapshots'][0],doc['snapshots'][0])

    @unittest.skipUnless(os.name=='nt','Windows encryption')
    def test_oauth_encryption_pkce_callback_replay_and_token_refresh(self):
        client={'installed':{'client_id':'test.apps.googleusercontent.com','client_secret':'test-client-secret'}}
        auth.configure(client)
        self.assertNotIn(b'test-client-secret',auth.vault_path().read_bytes())
        with patch.object(auth.webbrowser,'open',return_value=True) as opened:
            auth.start(8765)
        query=parse_qs(urlparse(opened.call_args.args[0]).query)
        self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertEqual(set(query['scope'][0].split()),set(auth.SCOPES))
        token={'access_token':'test-access','refresh_token':'test-refresh','expires_in':1,'scope':' '.join(auth.SCOPES)}
        with patch.object(auth,'request_json',side_effect=[token,{'items':[{'id':CHANNEL,'snippet':{'title':'Channel'}}]}]) as requests:
            self.assertTrue(auth.finish({'state':query['state'],'code':['test-code']},8765)['connected'])
            self.assertIn('code_verifier',requests.call_args_list[0].kwargs['form'])
        with self.assertRaises(ValueError):auth.finish({'state':query['state'],'code':['test-code']},8765)
        raw=auth.vault_path().read_bytes()
        for secret in [b'test-access',b'test-refresh']:self.assertNotIn(secret,raw)
        self.assertNotIn('access_token',json.dumps(auth.status()))
        with patch.object(auth,'request_json',return_value={'access_token':'new-access','expires_in':3600}):
            self.assertEqual(auth.access()[0],'new-access')
        self.assertEqual(auth.read_vault()['tokens']['refresh_token'],'test-refresh')

    def test_google_errors_never_leak_tokens_or_untrusted_redirects(self):
        error=urllib.error.HTTPError('https://secret-url?token=should-not-leak',403,'error',{},io.BytesIO(b'{"error":{"message":"private detail"}}'))
        with patch.object(urllib.request.OpenerDirector,'open',side_effect=error):
            with self.assertRaises(auth.GoogleError) as raised:auth.request_json('https://oauth2.googleapis.com/token',form={'refresh_token':'secret'})
        self.assertNotIn('private detail',str(raised.exception))
        self.assertNotIn('should-not-leak',str(raised.exception))
        with self.assertRaises(ValueError):auth.request_json('https://evil.test',bearer='secret')
        self.assertIsNone(auth.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test'))


if __name__=='__main__':unittest.main()
