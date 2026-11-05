import base64
import hashlib
import hmac
import io
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from ims.core import Store,stamp
from ims.app import make_app
from ims import experiments

class SystemTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(self.temp.name+'/test.sqlite3')
        self.keys=self.store.create_tenant('a',origins=['https://shop.example'],shop='a.myshopify.com',shop_secret='test-only')
        self.other=self.store.create_tenant('b')
        self.app=make_app(self.store)
    def tearDown(self):self.temp.cleanup()
    def request(self,path,method='GET',data=None,token=None,headers=None):
        route,_,query=path.partition('?');body=json.dumps(data).encode() if data is not None else b''
        env={'REQUEST_METHOD':method,'PATH_INFO':route,'QUERY_STRING':query,'CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body)}
        if token:env['HTTP_AUTHORIZATION']='Bearer '+token
        env.update(headers or {})
        response={}
        def start(status,h):response.update(status=int(status.split()[0]),headers=dict(h))
        raw=b''.join(self.app(env,start));response['body']=json.loads(raw) if raw else None
        return response
    def touch(self,event,visitor,source,day,medium='cpc',campaign='c1',order=None):
        self.store.touch('a',{'event_id':event,'visitor_id':visitor,'source':source,'medium':medium,'campaign':campaign,
                             'ts':f'2026-10-{day:02}T12:00:00Z','analytics_consent':True,**({'order_id':order} if order else {})},trusted=True)
    def order(self,order='o1',visitor='v1',value='100',day=10):
        self.store.order('a',{'order_id':order,'visitor_id':visitor,'ts':f'2026-10-{day:02}T13:00:00Z','currency':'USD','revenue':value})
    def report(self,model='last_touch',agency=False):return self.store.report('a','2026-10-01','2026-10-31',model,agency)
    def test_model_credit_conserves_revenue_and_orders(self):
        self.touch('e1','v1','google',1);self.touch('e2','v1','meta',2);self.touch('e3','v1','simplifi',3)
        self.order()
        for model in ['first_touch','last_touch','linear','position_based']:
            rows=self.report(model)
            self.assertAlmostEqual(sum(r['orders'] for r in rows),1,places=7)
            self.assertAlmostEqual(sum(r['revenue'] for r in rows),100,places=5)
        self.assertEqual(self.report('first_touch')[0]['channel'],'google_ads')
        self.assertEqual(self.report('last_touch')[0]['channel'],'simplifi')
    def test_future_touch_not_attributed(self):
        self.order(day=2);self.touch('e1','v1','meta',3)
        self.assertEqual(self.report()[0]['channel'],'unattributed')
    def test_direct_does_not_overwrite_paid(self):
        self.touch('e1','v1','google',1);self.touch('e2','v1','direct',2,medium='');self.order()
        self.assertEqual(self.report()[0]['channel'],'google_ads')
    def test_expired_touch_not_attributed(self):
        self.touch('e1','v1','google',1)
        self.store.order('a',{'order_id':'o','visitor_id':'v1','ts':'2026-11-03T00:00:00Z','currency':'USD','revenue':100})
        self.assertEqual(self.store.report('a','2026-11-01','2026-11-04')[0]['channel'],'unattributed')
    def test_order_replay_and_conflict(self):
        self.order();self.order();self.assertEqual(sum(r['orders'] for r in self.report()),1)
        with self.assertRaises(ValueError):self.order(value=200)
    def test_refunds_restate_and_cap_zero(self):
        self.order()
        r={'refund_id':'r1','order_id':'o1','amount':40,'ts':'2026-10-20T00:00:00Z'}
        self.store.refund('a',r);self.store.refund('a',r)
        self.assertEqual(self.report()[0]['revenue'],60)
        self.store.refund('a',{**r,'refund_id':'r2','amount':100})
        self.assertEqual(self.report()[0]['revenue'],0)
    def test_money_and_markup_denominators(self):
        self.touch('e','v1','google',1);self.order(value=600)
        self.store.spend('a',[{'date':'2026-10-10','channel':'google_ads','campaign':'c1','currency':'USD','cost':'100','impressions':10000,'clicks':100}])
        self.store.markup('a','*','2026-01-01',10000)
        row=self.report()[0]
        self.assertEqual(row['media_cost'],200);self.assertEqual(row['roas'],3)
        self.assertEqual(row['cpa'],200);self.assertEqual(row['cpc'],2);self.assertEqual(row['cpm'],20)
        self.assertNotIn('vendor_cost',row)
        self.assertEqual(self.report(agency=True)[0]['vendor_cost'],100)
    def test_effective_channel_markup(self):
        self.store.spend('a',[{'date':'2026-10-10','channel':'meta','campaign':'c','currency':'USD','cost':'100','impressions':0,'clicks':0}])
        self.store.markup('a','*','2026-01-01',10000);self.store.markup('a','meta','2026-10-01',5000)
        self.store.markup('a','meta','2026-10-11',0)
        self.assertEqual(self.report()[0]['media_cost'],150)
    def test_spend_upsert_not_append(self):
        r={'date':'2026-10-10','channel':'meta','campaign':'c','currency':'USD','cost':'100','impressions':1,'clicks':1}
        self.store.spend('a',[r]);self.store.spend('a',[{**r,'cost':50}])
        self.assertEqual(self.report()[0]['media_cost'],50)
    def test_currency_rejected(self):
        with self.assertRaises(ValueError):self.store.order('a',{'order_id':'o','ts':'2026-10-01T00:00:00Z','currency':'EUR','revenue':100})
    def test_client_cannot_mutate_or_request_agency_view(self):
        r=self.request('/api/markup','POST',{'effective':'2026-10-01','basis_points':10000},self.keys['client_token'])
        self.assertEqual(r['status'],403)
        self.order()
        r=self.request('/api/report?start=2026-10-01&end=2026-10-31&agency=true&tenant=b',token=self.keys['client_token'])
        self.assertEqual(r['status'],200);self.assertNotIn('vendor_cost',r['body']['rows'][0])
    def test_tenant_isolation(self):
        self.order()
        r=self.request('/api/report?start=2026-10-01&end=2026-10-31&tenant=a',token=self.other['client_token'])
        self.assertEqual(r['body']['rows'],[])
    def test_invalid_token(self):self.assertEqual(self.request('/api/customers',token='bad')['status'],401)
    def test_consent_denied_does_not_store_identity(self):
        self.assertEqual(self.store.touch('a',{'analytics_consent':False})['status'],'consent_denied')
        with self.store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM touches').fetchone()[0],0)
    def test_cors_and_bridge_authorization(self):
        self.assertEqual(self.request('/collect/a','POST',{},headers={'HTTP_ORIGIN':'https://bad.example'})['status'],403)
        self.assertEqual(self.request('/bridge/a','POST',{})['status'],401)
    def test_browser_cannot_create_revenue(self):
        data={'event_id':'event','visitor_id':'v','analytics_consent':True,'order_id':'o','revenue':99999}
        r=self.request('/collect/a','POST',data,headers={'HTTP_ORIGIN':'https://shop.example'})
        self.assertEqual(r['status'],202);self.assertEqual(self.report(),[])
    def test_shopify_signed_replayed_and_invalid(self):
        data={'id':123,'subtotal_price':'120.00','currency':'USD','created_at':'2026-10-10T00:00:00Z','customer':{'id':99}}
        raw=json.dumps(data).encode();signature=base64.b64encode(hmac.new(b'test-only',raw,hashlib.sha256).digest()).decode()
        h={'HTTP_X_SHOPIFY_SHOP_DOMAIN':'a.myshopify.com','HTTP_X_SHOPIFY_HMAC_SHA256':signature,'HTTP_X_SHOPIFY_WEBHOOK_ID':'delivery1','HTTP_X_SHOPIFY_TOPIC':'orders/paid'}
        self.assertEqual(self.request('/shopify/a','POST',data,headers=h)['status'],200)
        self.assertEqual(self.request('/shopify/a','POST',data,headers=h)['body']['status'],'duplicate')
        self.assertEqual(self.report()[0]['revenue'],120)
        self.assertEqual(self.request('/shopify/a','POST',data,headers={**h,'HTTP_X_SHOPIFY_HMAC_SHA256':'bad'})['status'],401)
    def test_late_observation_links_signed_order(self):
        self.order(visitor=None)
        self.touch('e1','v1','google',1)
        self.touch('e2','v1','direct',11,medium='',order='o1')
        self.assertEqual(self.report()[0]['channel'],'google_ads')
    def test_refund_before_order_is_reconciled(self):
        self.store.refund('a',{'refund_id':'r','order_id':'o1','amount':25,'ts':'2026-10-11T00:00:00Z'})
        self.order();self.assertEqual(self.report()[0]['revenue'],75)
    def test_no_division_by_zero(self):
        self.order(value=0)
        row=self.report()[0];self.assertIsNone(row['roas']);self.assertIsNone(row['cpc'])
    def test_experiment_enrollment_zero_outcomes_and_lift(self):
        future=datetime.now(timezone.utc)+timedelta(days=2);end=future+timedelta(days=7)
        experiments.create(self.store,'a',{'id':'lift','start':future.isoformat(),'end':end.isoformat(),'unit_type':'customer','hypothesis':'Ads increase revenue per eligible customer','min_units_per_arm':20})
        for i in range(100):experiments.enroll(self.store,'a','lift','u'+str(i))
        self.assertEqual(experiments.enroll(self.store,'a','lift','u1'),experiments.enroll(self.store,'a','lift','u1'))
        outcome_ts=(future+timedelta(days=1)).isoformat()
        after=(end+timedelta(days=1)).isoformat(timespec='microseconds')
        with patch('ims.experiments.now',return_value=after):
            with self.store.db() as db:units=db.execute("SELECT * FROM units WHERE experiment='lift'").fetchall()
            for i,u in enumerate(units):
                if u['arm']=='treatment':experiments.outcome(self.store,'a','lift',{'outcome_id':'x'+str(i),'unit':u['unit'],'ts':outcome_ts,'revenue':10})
            r=experiments.analyze(self.store,'a','lift',incremental_media_cost=100,iterations=200)
            self.assertEqual(r['treatment_units']+r['control_units'],100)
            self.assertEqual(r['revenue_lift_per_unit'],10)
            self.assertEqual(r['conversion_rate_control'],0)
            self.assertLess(r['p_value'],.05)
            self.assertEqual(r['status'],'final')
            with self.assertRaises(ValueError):experiments.enroll(self.store,'a','lift','late')
    def test_customer_summary_no_raw_customers(self):
        self.store.order('a',{'order_id':'o','ts':'2026-10-01T00:00:00Z','currency':'USD','revenue':100,'customer_id':'pseudonymous'})
        r=self.store.customer_summary('a');self.assertEqual(r['known_customers'],1);self.assertNotIn('pseudonymous',json.dumps(r))

if __name__=='__main__':unittest.main()
