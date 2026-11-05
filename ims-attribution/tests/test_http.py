import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from wsgiref.simple_server import make_server,WSGIRequestHandler
from ims.core import Store
from ims.app import make_app

class Quiet(WSGIRequestHandler):
    def log_message(self,*args):pass

class HTTPTests(unittest.TestCase):
    def test_real_http_console_sdk_readiness_and_auth(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d+'/db');keys=store.create_tenant('demo')
            with make_server('127.0.0.1',0,make_app(store),handler_class=Quiet) as server:
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(server.server_port)
                try:
                    with urllib.request.urlopen(base+'/ready') as r:self.assertEqual(json.load(r)['status'],'ready')
                    with urllib.request.urlopen(base+'/') as r:
                        self.assertIn('Attribution workspace',r.read().decode());self.assertIn('frame-ancestors',r.headers['Content-Security-Policy'])
                    with urllib.request.urlopen(base+'/pixel.js') as r:self.assertIn('IMSAttribution',r.read().decode())
                    with self.assertRaises(urllib.error.HTTPError) as denied:urllib.request.urlopen(base+'/api/status')
                    self.assertEqual(denied.exception.code,401)
                    request=urllib.request.Request(base+'/api/status',headers={'Authorization':'Bearer '+keys['client_token']})
                    with urllib.request.urlopen(request) as r:self.assertIn('jobs',json.load(r))
                finally:server.shutdown();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
