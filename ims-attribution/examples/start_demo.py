"""Loopback-only synthetic demo; never forwards ads or writes production data."""
import sys
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from wsgiref.simple_server import make_server,WSGIRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ims.core import Store
from ims.app import make_app

class QuietHandler(WSGIRequestHandler):
    def log_message(self,*args):pass

with tempfile.TemporaryDirectory() as d:
    s=Store(d+'/demo.sqlite3');keys=s.create_tenant('demo',origins=['https://demo.example.com'])
    day=datetime.now(timezone.utc).date().isoformat()
    for i,channel in enumerate(['google_ads','meta','ctv']):
        s.spend('demo',[{'date':day,'channel':channel,'campaign':'campaign-'+str(i),'currency':'USD','cost':100*(i+1),'impressions':10000*(i+1),'clicks':100*(i+1)}])
    for i in range(6):
        v='visitor-'+str(i);ts=day+'T00:00:00Z'
        s.touch('demo',{'event_id':'event-'+str(i),'visitor_id':v,'source':'google' if i<3 else 'meta','medium':'cpc','campaign':'campaign-0' if i<3 else 'campaign-1','ts':ts,'analytics_consent':True},trusted=True)
        s.order('demo',{'order_id':'order-'+str(i),'visitor_id':v,'ts':day+'T00:01:00Z','currency':'USD','revenue':200+i*20})
    s.markup('demo','*','2020-01-01',10000)
    print('Synthetic demo: http://127.0.0.1:8085',flush=True)
    print('Temporary agency token: '+keys['agency_token'],flush=True)
    print('Temporary client token: '+keys['client_token'],flush=True)
    print('No live vendors connected. Ctrl-C removes the temporary database.',flush=True)
    try:
        with make_server('127.0.0.1',8085,make_app(s),handler_class=QuietHandler) as server:server.serve_forever()
    except KeyboardInterrupt:pass
