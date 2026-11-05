"""WSGI API. Run behind TLS + a rate-limiting reverse proxy; see deployment guide."""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs
from .core import Store, digest, ident, now
from . import experiments,ctv,connectors,privacy,operations,publications,commerce_privacy,delivery_admin

MAX_BODY=1024*1024
ROOT=Path(__file__).resolve().parent.parent

class HTTPError(Exception):
    def __init__(self,status,message):
        self.status,self.message=status,message

def make_app(store):
    def app(env,start_response):
        status=200; headers=[('Content-Type','application/json'),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]
        def respond(code,payload):
            start_response(f'{code} '+{200:'OK',202:'Accepted',204:'No Content',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',413:'Payload Too Large',500:'Internal Server Error'}[code],headers)
            return [json.dumps(payload,allow_nan=False,separators=(',',':')).encode() if code!=204 else b'']
        try:
            method,path=env['REQUEST_METHOD'],env.get('PATH_INFO','/')
            if path=='/health' and method=='GET':
                return respond(200,{'status':'ok','version':'1.0.0'})
            if path=='/ready' and method=='GET':
                with store.db() as db:db.execute('SELECT 1').fetchone()
                return respond(200,{'status':'ready'})
            if path in {'/','/pixel.js'} and method=='GET':
                file=ROOT/'web'/('index.html' if path=='/' else 'pixel.js')
                headers[0]=('Content-Type','text/html; charset=utf-8' if path=='/' else 'application/javascript')
                headers.append(('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"))
                start_response('200 OK',headers)
                return [file.read_bytes()]
            public=re.fullmatch(r'/collect/([A-Za-z0-9_.:-]+)',path)
            if public:
                tenant=public.group(1); t=store.tenant(tenant)
                origin=env.get('HTTP_ORIGIN','')
                if origin not in json.loads(t['origins']):
                    raise HTTPError(403,'Origin not allowed')
                headers.extend([('Access-Control-Allow-Origin',origin),('Vary','Origin'),
                                ('Access-Control-Allow-Methods','POST, OPTIONS'),('Access-Control-Allow-Headers','Content-Type')])
                if method=='OPTIONS':
                    return respond(204,{})
            if method not in {'GET','POST'}:
                raise HTTPError(405,'Method not allowed')
            length=int(env.get('CONTENT_LENGTH') or 0)
            if not 0<=length<=MAX_BODY:
                raise HTTPError(413,'Body too large')
            raw=env['wsgi.input'].read(length) if method=='POST' else b''
            data=json.loads(raw) if raw else {}
            if not isinstance(data,dict):
                raise ValueError('Expected JSON object')
            generic=re.fullmatch(r'/ingest/([A-Za-z0-9_.:-]+)/([A-Za-z0-9_.:-]+)',path)
            if generic and method=='POST':
                return respond(202,connectors.ingest(store,*generic.groups(),{
                    'timestamp':env.get('HTTP_X_IMS_TIMESTAMP',''),
                    'delivery':env.get('HTTP_X_IMS_DELIVERY',''),
                    'signature':env.get('HTTP_X_IMS_SIGNATURE','')},raw))
            if public:
                return respond(202,store.touch(tenant,data))
            bridge=re.fullmatch(r'/bridge/([A-Za-z0-9_.:-]+)',path)
            if bridge and method=='POST':
                tenant=bridge.group(1); t=store.tenant(tenant)
                key=env.get('HTTP_X_IMS_BRIDGE_KEY','')
                if not hmac.compare_digest(digest(key),t['bridge_hash']):
                    raise HTTPError(401,'Invalid bridge credential')
                return respond(202,store.touch(tenant,data,trusted=True))
            webhook=re.fullmatch(r'/shopify/([A-Za-z0-9_.:-]+)',path)
            if webhook and method=='POST':
                return respond(200,shopify(store,webhook.group(1),env,raw,data))
            token=env.get('HTTP_AUTHORIZATION','').removeprefix('Bearer ')
            auth=store.auth(token)
            if not auth:
                raise HTTPError(401,'Valid bearer credential required')
            tenant,role=auth['tenant'],auth['role']
            qs=parse_qs(env.get('QUERY_STRING',''))
            q=lambda k,default=None:qs.get(k,[default])[0]
            if path=='/api/session' and method=='GET':
                return respond(200,{'tenant':tenant,'role':role})
            if path=='/api/report' and method=='GET':
                # Tenant comes only from token; never from a URL or query parameter.
                return respond(200,{'rows':store.report(tenant,q('start'),q('end'),q('model','last_touch'),agency=role=='agency')})
            if path=='/api/customers' and method=='GET':
                return respond(200,store.customer_summary(tenant))
            if path=='/api/status' and method=='GET':
                return respond(200,operations.status(store,tenant))
            if path=='/api/experiments/published' and method=='GET':
                return respond(200,{'rows':publications.listed(store,tenant)})
            if path=='/api/ctv/report' and method=='GET':
                return respond(200,ctv.report(store,tenant,q('start'),q('end'),q('window_hours',168)))
            if role!='agency':
                raise HTTPError(403,'Agency access required')
            actor=digest(token)[:12]
            if path=='/api/deliveries/retry' and method=='POST':
                return respond(200,delivery_admin.retry(store,tenant,data,actor))
            if path=='/api/privacy/requests' and method=='GET':
                return respond(200,{'rows':commerce_privacy.requests(store,tenant)})
            publication=re.fullmatch(r'/api/experiments/([A-Za-z0-9_.:-]+)/(publish|unpublish)',path)
            if publication and method=='POST':
                experiment,action=publication.groups()
                return respond(200,publications.publish(store,tenant,experiment,data,actor) if action=='publish' else publications.unpublish(store,tenant,experiment,actor))
            if path=='/api/privacy/withdraw' and method=='POST':
                return respond(200,privacy.withdraw(store,tenant,data['visitor_id'],data.get('erase_analytics') is True,actor))
            if path=='/api/privacy/fresh-grant' and method=='POST':
                return respond(200,privacy.fresh_grant(store,tenant,data['visitor_id'],actor))
            if path=='/api/connectors':
                if method=='POST':return respond(200,connectors.register(store,tenant,data))
                if method=='GET':return respond(200,{'rows':connectors.catalog(store,tenant)})
            if path=='/api/ctv/impressions' and method=='POST':
                ctv.impressions(store,tenant,data['rows'])
                return respond(200,{'status':'saved'})
            if path=='/api/ctv/order-networks' and method=='POST':
                ctv.link_orders(store,tenant,data['rows'])
                return respond(200,{'status':'saved'})
            ctv_match=re.fullmatch(r'/api/ctv/experiments/([A-Za-z0-9_.:-]+)/(enroll|sync-outcomes)',path)
            if ctv_match and method=='POST':
                exp,action=ctv_match.groups()
                return respond(200,ctv.enroll_ip(store,tenant,exp,data) if action=='enroll' else ctv.sync_outcomes(store,tenant,exp))
            if path=='/api/markup' and method=='POST':
                store.markup(tenant,data.get('channel','*'),data['effective'],data['basis_points'],actor)
                return respond(200,{'status':'saved'})
            if path=='/api/spend' and method=='POST':
                store.spend(tenant,data['rows'],actor)
                return respond(200,{'status':'saved'})
            if path in {'/api/orders','/api/refunds'} and method=='POST':
                with store.db() as db:
                    for row in data['rows']:
                        (store.order if path=='/api/orders' else store.refund)(tenant,row,db)
                    store.audit(db,tenant,actor,'trusted_import',{'type':path,'rows':len(data['rows'])})
                return respond(200,{'status':'saved'})
            if path=='/api/audit' and method=='GET':
                with store.db() as db:
                    rows=[dict(r) for r in db.execute('SELECT ts,actor,action,detail FROM audit WHERE tenant=? ORDER BY id DESC LIMIT 100',(tenant,))]
                return respond(200,{'rows':rows})
            if path=='/api/experiments' and method=='POST':
                return respond(200,experiments.create(store,tenant,data))
            match=re.fullmatch(r'/api/experiments/([A-Za-z0-9_.:-]+)/(enroll|outcomes|results)',path)
            if match:
                experiment,action=match.groups()
                if action=='enroll' and method=='POST':
                    return respond(200,experiments.enroll(store,tenant,experiment,data['unit']))
                if action=='outcomes' and method=='POST':
                    experiments.outcome(store,tenant,experiment,data)
                    return respond(200,{'status':'saved'})
                if action=='results' and method=='GET':
                    return respond(200,experiments.analyze(store,tenant,experiment,q('incremental_media_cost')))
            raise HTTPError(404,'Not found')
        except HTTPError as e:
            return respond(e.status,{'error':e.message})
        except PermissionError:
            return respond(403,{'error':'Connector authorization failed'})
        except (ValueError,KeyError,TypeError,ArithmeticError):
            return respond(400,{'error':'Invalid or conflicting input; check schema, currency, timestamps and IDs'})
        except Exception:
            # Do not log request bodies, raw spend, customer data or credentials.
            return respond(500,{'error':'Internal error; inspect server health without logging payloads'})
    return app

def shopify(store,tenant,env,raw,data):
    t=store.tenant(tenant,allow_closed=True)
    if not t['shop_secret'] or env.get('HTTP_X_SHOPIFY_SHOP_DOMAIN')!=t['shop']:
        raise HTTPError(401,'Unknown Shopify shop')
    signature=base64.b64encode(hmac.new(t['shop_secret'].encode(),raw,hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(signature,env.get('HTTP_X_SHOPIFY_HMAC_SHA256','')):
        raise HTTPError(401,'Invalid Shopify signature')
    delivery=ident(env.get('HTTP_X_SHOPIFY_WEBHOOK_ID',''))
    topic=env.get('HTTP_X_SHOPIFY_TOPIC','')
    if topic in {'customers/data_request','customers/redact','shop/redact'}:
        return commerce_privacy.handle(store,tenant,topic,delivery,data)
    store.tenant(tenant)
    if topic not in {'orders/paid','refunds/create'}:
        raise ValueError('Unsupported topic')
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM deliveries WHERE tenant=? AND delivery=?',(tenant,delivery)).fetchone():
            return {'status':'duplicate'}
        if topic=='orders/paid':
            if data.get('test') is True:
                return {'status':'test_order_ignored'}
            # Store subtotal after discounts, excluding shipping/tax; refunds use line subtotals.
            customer=str((data.get('customer') or {}).get('id') or '')
            anon=hmac.new(t['shop_secret'].encode(),customer.encode(),hashlib.sha256).hexdigest() if customer else None
            visitor=next((a['value'] for a in data.get('note_attributes',[]) if a.get('name')=='ims_visitor_id'),None)
            oid=str(data['id'])
            existing=db.execute('SELECT currency FROM orders WHERE tenant=? AND order_id=?',(tenant,oid)).fetchone()
            if existing:
                if existing['currency']!=data['currency']:raise ValueError('Currency conflict')
                # A reconciliation snapshot may arrive before this webhook. Do not overwrite
                # its authoritative state or fail simply because source labels differ.
                if visitor:db.execute('UPDATE orders SET visitor=COALESCE(visitor,?) WHERE tenant=? AND order_id=?',(ident(visitor),tenant,oid))
                if anon:db.execute('UPDATE orders SET customer=COALESCE(customer,?) WHERE tenant=? AND order_id=?',(anon,tenant,oid))
            else:
                store.order(tenant,{'order_id':oid,'visitor_id':visitor,'ts':data['created_at'],
                                    'currency':data['currency'],'revenue':data['subtotal_price'],
                                    'customer_id':anon,'source':'shopify_paid'},db)
        else:
            # All amounts in shop currency. Adjustments/shipping refunds require reconciliation.
            from decimal import Decimal
            amount=sum((Decimal(str(r['subtotal'])) for r in data.get('refund_line_items',[])),Decimal(0))
            store.refund(tenant,{'refund_id':str(data['id']),'order_id':str(data['order_id']),
                                 'amount':str(amount),'ts':data['created_at']},db)
        db.execute('INSERT INTO deliveries VALUES(?,?,?)',(tenant,delivery,now()))
    return {'status':'accepted'}

def application_factory():
    path=os.environ.get('IMS_DB','/data/ims.sqlite3')
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    return make_app(Store(path))
