import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import RunManager, make_server
from cli_backends import Cancelled


def logic(cancel, **kwargs):
    return {'available': True} if kwargs.get('probe') else {'engine':'PyreWire', 'order':['install','claude_md','facts','bookkeeping']}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.calls=[]
        def generate(prompt, model, cancel, timeout, **kwargs):
            self.calls.append((prompt,model,kwargs))
            return {'answer':'운영 규칙 · facts 파일', 'models':['fixture']}
        self.manager=RunManager(root=self.tmp.name, generator=generate, logic=logic)
        self.http=make_server(0,self.manager)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        if self.manager.active:self.manager.cancel(self.manager.active)
        if self.manager.worker:self.manager.worker.join(2)
        self.http.shutdown();self.http.server_close();self.tmp.cleanup()
    def request(self, method, path, body=None, **headers):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        if body is not None: body=json.dumps(body)
        headers.setdefault('X-Run-Token', self.http.token)
        connection.request(method,path,body=body,headers=headers)
        response=connection.getresponse();data=response.read();connection.close()
        return response.status, data
    def test_rag_snapshot_and_persistence(self):
        for backend in ['claude','cursor','copilot','agy','codex']:
            ident=self.manager.start('rag',6,backend);self.manager.worker.join(3)
            run=self.manager.snapshot(ident)
            self.assertEqual(run['status'],'completed')
            self.assertEqual(len(run['calls']),2)
            self.assertEqual(len(run['retrieved']),6)
            self.assertEqual(self.calls[-1][2]['backend'],backend)
            self.assertNotIn(run['procedure_card'],run['calls'][0]['prompt'])
            self.assertIn(run['procedure_card'],run['calls'][1]['prompt'])
            saved=json.loads((Path(self.tmp.name)/ident/'result.json').read_text())
            self.assertEqual(saved,json.loads(json.dumps(run)))
    def test_failed_second_call_preserves_first(self):
        def generate(*args,**kwargs):
            if self.calls:raise RuntimeError('second failed')
            self.calls.append(1);return {'answer':'first'}
        self.manager.generator=generate
        ident=self.manager.start('rag');self.manager.worker.join(3)
        run=self.manager.snapshot(ident)
        self.assertEqual(run['status'],'failed');self.assertEqual(run['calls'][0]['answer'],'first')
        self.assertEqual(run['calls'][1]['status'],'failed')
        self.assertTrue((Path(self.tmp.name)/ident/'result.json').exists())
    def test_single_active_cancel_and_freeze(self):
        entered=threading.Event()
        def generate(prompt,model,cancel,*args,**kwargs):
            entered.set();cancel.wait(3);raise Cancelled()
        self.manager.generator=generate
        ident=self.manager.start('rag',1,'codex');entered.wait(1)
        with self.assertRaises(RuntimeError):self.manager.start('logic')
        self.manager.cancel(ident);self.manager.worker.join(3)
        self.assertEqual(self.manager.snapshot(ident)['status'],'cancelled')
        self.assertIsNone(self.manager.active)
    def test_invalid_inputs(self):
        for k in [True,0,7,'2',None]:
            with self.assertRaises(ValueError):self.manager.start('rag',k)
        with self.assertRaises(ValueError):self.manager.start('other')
        with self.assertRaises(ValueError):self.manager.start('rag',2,'bad')
    def test_http_security_and_static_allowlist(self):
        self.assertEqual(self.request('GET','/api/status')[0],200)
        for path in ['/server.py','/runs/a/result.json','/../README.md']:
            self.assertEqual(self.request('GET',path)[0],404)
        self.assertEqual(self.request('GET','/',Host='evil.example')[0],403)
        self.assertEqual(self.request('POST','/api/runs',{'kind':'logic'},Origin='http://evil.example')[0],403)
        self.assertEqual(self.request('POST','/api/runs',{'kind':'logic'},**{'X-Run-Token':''})[0],403)
        self.assertEqual(self.request('POST','/api/runs',[],)[0],400)
        self.assertEqual(self.request('POST','/api/runs',{'kind':'other'})[0],400)
    def test_unavailable_modes_and_logic(self):
        with patch('server.shutil.which',return_value=None):
            self.assertEqual(self.request('POST','/api/runs',{'kind':'rag'})[0],503)
        code,data=self.request('POST','/api/runs',{'kind':'logic'})
        self.assertEqual(code,202);self.manager.worker.join(3)
        ident=json.loads(data)['id']
        self.assertEqual(self.request('GET','/api/runs/'+ident)[0],200)
        self.manager.logic_status={'available':False,'detail':'missing'}
        self.assertEqual(self.request('POST','/api/runs',{'kind':'logic'})[0],503)

if __name__=='__main__':unittest.main()
