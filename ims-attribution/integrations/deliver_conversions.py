"""Durable at-least-once verified-purchase forwarding to a configured sGTM gateway.
Acknowledgement means gateway accepted, NOT Meta/Google/Simpli.fi attribution.
No advertising identifiers, email, IP or user agent are fabricated.
"""
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
from ims.core import Store,now

def enqueue(store):
    with store.db() as db:
        for r in db.execute('SELECT o.tenant,o.order_id FROM orders o JOIN observations x ON x.tenant=o.tenant AND x.order_id=o.order_id WHERE x.marketing=1'):
            event=hashlib.sha256((r['tenant']+':purchase:'+r['order_id']).encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO outbox(tenant,order_id,event_id,next_attempt) VALUES(?,?,?,?)',(r['tenant'],r['order_id'],event,now()))

def deliver(store,config,limit=100):
    enqueue(store)
    if not config:return
    tenants=list(config)
    with store.db() as db:
        rows=db.execute("SELECT b.*,o.gross,o.currency,o.ts,x.visitor,x.marketing FROM outbox b JOIN orders o ON o.tenant=b.tenant AND o.order_id=b.order_id JOIN observations x ON x.tenant=b.tenant AND x.order_id=b.order_id WHERE b.state='pending' AND b.next_attempt<=? AND b.tenant IN ("+','.join('?' for _ in tenants)+") ORDER BY b.next_attempt LIMIT ?",(now(),*tenants,limit)).fetchall()
    for r in rows:
        settings=config.get(r['tenant'])
        if not settings:continue
        endpoint=settings['endpoint']; parsed=urlsplit(endpoint)
        if parsed.scheme!='https' or parsed.path!='/ims/verified' or parsed.username or parsed.password:
            raise ValueError('Use fixed HTTPS sGTM endpoint ending /ims/verified')
        if not r['marketing']:
            with store.db() as db:db.execute("UPDATE outbox SET state='consent_blocked' WHERE tenant=? AND order_id=?",(r['tenant'],r['order_id']))
            continue
        payload={'event_name':'purchase','event_id':r['event_id'],'transaction_id':r['order_id'],
                 'value':r['gross']/100,'currency':r['currency'],'client_id':r['visitor'],
                 'event_time':int(datetime.fromisoformat(r['ts']).timestamp()),
                 'analytics_consent':True,'marketing_consent':True,'action_source':'website'}
        with store.db() as db:
            signals=db.execute('SELECT payload FROM signals WHERE tenant=? AND visitor=?',(r['tenant'],r['visitor'])).fetchone()
        if signals:payload.update(json.loads(signals['payload']))
        origins=json.loads(store.tenant(r['tenant'])['origins'])
        if origins:payload['event_source_url']=origins[0]+'/'
        req=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),
               headers={'Content-Type':'application/json','X-IMS-Gateway-Key':settings['key']})
        status=0
        # Do not follow redirects that could leak the gateway secret.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):return None
        try:
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as response:status=response.status
        except urllib.error.HTTPError as e:status=e.code
        except (urllib.error.URLError,TimeoutError):pass
        attempts=r['attempts']+1
        state='gateway_accepted' if 200<=status<300 else ('dead_letter' if attempts>=8 else 'pending')
        next_attempt=(datetime.now(timezone.utc)+timedelta(seconds=min(3600,30*2**attempts))).isoformat(timespec='microseconds')
        with store.db() as db:
            db.execute('UPDATE outbox SET attempts=?,next_attempt=?,state=?,last_status=? WHERE tenant=? AND order_id=?',
                       (attempts,next_attempt,state,status,r['tenant'],r['order_id']))

if __name__=='__main__':
    # Config file is server-only secret material; never export it to clients.
    with open(os.environ['IMS_GATEWAYS_FILE']) as f:config=json.load(f)
    deliver(Store(os.environ['IMS_DB']),config)
