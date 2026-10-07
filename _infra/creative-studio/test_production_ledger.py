import unittest, tempfile, json, threading, urllib.request, urllib.error
from pathlib import Path
import production_ledger as ledger
import server


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False) if not isinstance(data, (str, bytes)) else data, encoding='utf-8') if not isinstance(data, bytes) else path.write_bytes(data)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.p = self.root / 'productions/video/demo'; self.p.mkdir(parents=True)
        (self.p / 'BRIEF.md').write_text('story', encoding='utf-8')
        # cut 01: two image versions, two video versions (v001 adopted)
        for v in ('v001', 'v002'):
            d = self.p / f'shots/01/imagegen-{v}'
            write(d / 'planned-start.png', b'\x89PNG\r\n\x1a\n' + v.encode())
            write(d / 'request.json', {'model': 'gpt-image-2', 'size': '1024x1536', 'quality': 'high', 'generated_at': '2026-09-15T10:00:00+0900',
                                       'usage': {'input_tokens': 5000, 'input_tokens_details': {'image_tokens': 4000, 'text_tokens': 1000}, 'output_tokens': 5488}})
        for v, dur in (('v001', 6), ('v002', 5)):
            d = self.p / f'shots/01/h3-{v}'
            write(d / 'result.mp4', b'0123456789'); write(d / 'actual-end.png', b'\x89PNG\r\n\x1a\n'); write(d / 'first-frame.png', b'\x89PNG\r\n\x1a\n')
            write(d / 'request.json', {'model': 'minimax_h3', 'duration': dur, 'job_id': 'job-' + v})
            write(d / 'result.json', {'status': 'completed', 'duration': dur + 0.5, 'credits_est': dur * 2, 'collected_at': '2026-09-15T12:00:00+0900'})
            write(d / 'asr.json', {'text': '대사 ' + v})
        write(self.p / 'shots/01/h3-v002/registration.json', {'id': '01', 'status': 'review', 'video': 'shots/01/h3-v002/result.mp4', 'input_image': 'shots/01/imagegen-v002/planned-start.png', 'end_image': 'shots/01/h3-v002/actual-end.png', 'request_file': 'shots/01/h3-v002/request.json', 'duration': 5.5})
        write(self.p / 'assets/production/h3-v001/submitted-jobs-v001.json', {'jobs': [], 'failed_submissions': [{'cut_id': '01', 'error': '422'}]})
        write(self.p / 'project.json', {'schema_version': 1, 'id': 'demo', 'title': 'Demo', 'kind': 'video', 'full_video': None, 'cuts': [
            {'id': '01', 'name': 'One', 'status': 'review', 'video': 'shots/01/h3-v001/result.mp4', 'input_image': 'shots/01/imagegen-v001/planned-start.png', 'end_image': 'shots/01/h3-v001/actual-end.png', 'request_file': 'shots/01/h3-v001/request.json', 'duration': 6.5, 'start': None, 'planned_start_image': 'shots/01/imagegen-v001/planned-start.png'},
            {'id': '02', 'name': 'Two', 'status': 'planned', 'video': None, 'input_image': None, 'end_image': None, 'request_file': None, 'duration': None, 'start': None}]})
        write(self.p / 'exports/final-v001/youtube-publication.json', {'video_id': 'abcdefghijk', 'channel_id': 'UCdemo000000000000000000', 'status': 'scheduled', 'title': 'Demo Short', 'url': 'https://youtube.com/shorts/abcdefghijk', 'scheduled_publish_at': '2026-09-16T13:00:00+09:00', 'uploaded_at': '2026-09-15T17:43:20+0900', 'source': 'exports/final-v001/final.mp4'})
        write(self.p / 'exports/old-v001/youtube-publication.json', {'video_id': 'zzzzzzzzzzz', 'status': 'superseded_private', 'title': 'Old', 'uploaded_at': '2026-09-15T17:00:00+0900'})
        write(self.p / 'youtube-analytics.json', {'schema_version': 1, 'revision': 1, 'links': [{'video_id': 'abcdefghijk', 'title': 'Demo Short', 'published_date': '2026-09-16', 'url': 'https://youtube.com/shorts/abcdefghijk'}],
                                                  'snapshots': [{'id': 's1', 'video_id': 'abcdefghijk', 'as_of': '2026-09-16T10:00:00+09:00', 'source': 'studio_manual', 'metrics': {'views': 1400, 'stayedToWatch': 54.6}},
                                                                {'id': 's0', 'video_id': 'abcdefghijk', 'as_of': '2026-09-15T10:00:00+09:00', 'source': 'studio_manual', 'metrics': {'views': 100}}]})
        # A sibling project on another channel must never appear in the channel comparison.
        other = self.root / 'productions/video/other'; other.mkdir(parents=True); (other / 'BRIEF.md').write_text('x', encoding='utf-8')
        write(other / 'exports/v001/youtube-publication.json', {'video_id': 'otherotherO', 'channel_id': 'UCother00000000000000000', 'status': 'published', 'title': 'Other channel'})
        write(other / 'youtube-analytics.json', {'schema_version': 1, 'revision': 1, 'links': [], 'snapshots': [{'id': 'o1', 'video_id': 'otherotherO', 'as_of': '2026-09-16T10:00:00+09:00', 'source': 'youtube_api', 'metrics': {'views': 9999}}]})
        server.ROOT = self.root
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler); self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start(); self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, path, body=None):
        h = {}
        if body is not None: h.update({'X-Studio-Token': server.TOKEN, 'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=h)))

    def test_versions_costs_and_summary(self):
        images, videos = ledger.cut_versions(self.p, '01')
        self.assertEqual([v['label'] for v in images], ['v001', 'v002'])
        self.assertAlmostEqual(images[0]['cost_usd'], (4000 * 8 + 1000 * 5 + 5488 * 30) / 1e6, places=4)
        self.assertEqual([(v['label'], v['credits'], v['asr']) for v in videos], [('v001', 12, '대사 v001'), ('v002', 10, '대사 v002')])
        catalog = self.request('/api/project?id=productions/video/demo')
        cut = catalog['cuts'][0]
        self.assertEqual([v['adopted'] for v in cut['image_versions']], [True, False])
        self.assertEqual([v['adopted'] for v in cut['video_versions']], [True, False])
        self.assertEqual(cut['credits'], 12)
        L = catalog['ledger']
        self.assertEqual((L['image_count'], L['video_count'], L['retries'], L['credits_used'], L['failed_submissions'], L['pending_video_cuts'], L['pending_credits']), (2, 2, 1, 22, 1, 1, 12))
        self.assertIsNone(L['balance'])
        self.assertEqual([p['label'] for p in catalog['publications']], ['예약됨', '비공개 보존'])
        rows = catalog['channel']['rows']
        self.assertEqual(catalog['channel']['channel_id'], 'UCdemo000000000000000000')
        self.assertEqual([(r['video_id'], r['views'], r['over_wall']) for r in rows], [('abcdefghijk', 1400, True)])
        self.assertEqual(ledger.channel(self.root, server.projects(), None)['rows'], [])

    def test_adopt_image_and_video_keep_media_and_log(self):
        self.request('/api/adopt', {'project': 'productions/video/demo', 'cut': '01', 'kind': 'image', 'version': 'imagegen-v002'})
        contract = json.loads((self.p / 'project.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(contract['cuts'][0]['planned_start_image'], 'shots/01/imagegen-v002/planned-start.png')
        self.assertEqual(contract['cuts'][0]['video'], 'shots/01/h3-v001/result.mp4')
        self.request('/api/adopt', {'project': 'productions/video/demo', 'cut': '01', 'kind': 'video', 'version': 'h3-v002'})
        contract = json.loads((self.p / 'project.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(contract['cuts'][0]['video'], 'shots/01/h3-v002/result.mp4')
        self.assertEqual(contract['cuts'][0]['input_image'], 'shots/01/imagegen-v002/planned-start.png')
        self.assertEqual(contract['cuts'][0]['duration'], 5.5)
        self.assertTrue((self.p / 'shots/01/h3-v001/result.mp4').is_file())
        log = server.state(self.p)['adoptions']
        self.assertEqual([(a['kind'], a['version'], a['previous']) for a in log], [('image', 'imagegen-v002', 'shots/01/imagegen-v001/planned-start.png'), ('video', 'h3-v002', 'shots/01/h3-v001/result.mp4')])
        for bad in ({'kind': 'video', 'version': '../../BRIEF.md'}, {'kind': 'video', 'version': 'h3-v009'}, {'kind': 'audio', 'version': 'h3-v001'}, {'kind': 'image', 'version': 'h3-v001'}):
            with self.assertRaises(urllib.error.HTTPError):
                self.request('/api/adopt', {'project': 'productions/video/demo', 'cut': '01', **bad})
        with self.assertRaises(urllib.error.HTTPError):
            self.request('/api/adopt', {'project': 'productions/video/demo', 'cut': '99', 'kind': 'image', 'version': 'imagegen-v001'})

    def test_credits_balance_and_shortfall(self):
        self.request('/api/credits', {'service': 'higgsfield', 'balance': 7.5})
        L = self.request('/api/project?id=productions/video/demo')['ledger']
        self.assertEqual(L['balance']['balance'], 7.5); self.assertEqual(L['credits_short'], 4.5)
        for bad in ({'service': 'other', 'balance': 1}, {'service': 'higgsfield', 'balance': -1}, {'service': 'higgsfield', 'balance': 'x'}):
            with self.assertRaises(urllib.error.HTTPError): self.request('/api/credits', bad)
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(urllib.request.Request(self.base + '/api/credits', data=b'{}', headers={'Content-Type': 'application/json'}))


if __name__ == '__main__':
    unittest.main()
