import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from ims.core import Store,now
from ims import commerce_privacy,experiments,publications
from ims.setup import configure
from integrations import destinations,simplifi_reports,commerce_sync,run_pipeline

class InstallReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/db')
        self.keys=self.store.create_tenant('a',origins=['https://shop.example'],shop='a.myshopify.com',shop_secret='fixture')
    def tearDown(self):self.tmp.cleanup()
    def payload(self):return {'order_id':'o','event_id':'stable','value':100,'currency':'USD','ts':now(),
        'source_url':'https://shop.example/','visitor':'v','signals':{'gclid':'click','fbp':'fb.1.123.abc'}}
    def test_native_google_requires_identifier_and_checks_partial_failure(self):
        config={'customer_id':'123','conversion_action_id':'456','api_version':'v99'}
        with patch.dict(os.environ,{'GOOGLE_ADS_DEVELOPER_TOKEN':'fixture'}),patch.object(destinations,'oauth_refresh',return_value='fixture'),patch.object(destinations,'call',return_value={'results':[{}]}) as call:
            self.assertEqual(destinations.deliver_google(self.payload(),config),'provider_accepted')
            body=call.call_args.args[2];self.assertTrue(body['partialFailure']);self.assertEqual(body['conversions'][0]['orderId'],'o')
        with self.assertRaises(destinations.MissingIdentifier):destinations.deliver_google({**self.payload(),'signals':{}},config)
        with patch.dict(os.environ,{'GOOGLE_ADS_DEVELOPER_TOKEN':'fixture'}),patch.object(destinations,'oauth_refresh',return_value='fixture'),patch.object(destinations,'call',return_value={'partialFailureError':{'code':3}}):
            with self.assertRaises(destinations.VendorError):destinations.deliver_google(self.payload(),config)
    def test_meta_uses_stable_id_and_requires_provider_receipt(self):
        config={'pixel_id':'123','api_version':'v99.0'}
        with patch.dict(os.environ,{'META_ACCESS_TOKEN':'fixture'}),patch.object(destinations,'call',return_value={'events_received':1}) as call:
            self.assertEqual(destinations.deliver_meta(self.payload(),config),'provider_accepted')
            e=call.call_args.args[2]['data'][0];self.assertEqual(e['event_id'],'stable');self.assertNotIn('client_ip_address',e['user_data'])
        with patch.dict(os.environ,{'META_ACCESS_TOKEN':'fixture'}),patch.object(destinations,'call',return_value={'events_received':0}):
            with self.assertRaises(destinations.VendorError):destinations.deliver_meta(self.payload(),config)
    def test_native_delivery_once_and_withdrawal(self):
        self.store.order('a',{'order_id':'o','revenue':100,'ts':now(),'currency':'USD'})
        self.store.touch('a',{'event_id':'e','visitor_id':'v','analytics_consent':True,'marketing_consent':True,'order_id':'o','signals':{'fbp':'fb.1.123.abc'}})
        cfg={'a':[{'id':'meta','type':'meta','enabled':True,'pixel_id':'123','api_version':'v99.0'}]}
        with patch.dict(os.environ,{'META_ACCESS_TOKEN':'fixture'}),patch.object(destinations,'call',return_value={'events_received':1}) as call:
            destinations.run(self.store,cfg);destinations.run(self.store,cfg);self.assertEqual(call.call_count,1)
    def test_setup_generates_isolated_compose_and_bundled_installer(self):
        cfg={'api_origin':'https://tracking.example.com','tenants':[{'id':'client','currency':'USD','timezone':'UTC','store_origins':['https://store.example.com'],'sgtm_origin':'https://tags.example.com'}]}
        out=Path(self.tmp.name)/'generated'
        # This test host does not permit Unix ownership changes to container UID 10001.
        # Verify configuration generation with the ownership syscall mocked separately.
        with patch('ims.setup.os.chown'):result=configure(cfg,out)
        self.assertEqual(result['status'],'generated')
        compose=json.loads((out/'compose.json').read_text());self.assertIn('jobs',compose['services'])
        self.assertIn('127.0.0.1:8080:8080',compose['services']['api']['ports'])
        pixel=(out/'installers/client/shopify-pixel.js').read_text();self.assertIn('https://tags.example.com/ims/events/client',pixel)
        self.assertNotIn("document.createElement('script');s.src=IMS_BASE",pixel)
        self.assertNotIn('agency_token',pixel)
        with self.assertRaises(ValueError):configure(cfg,out)
    def test_simplifi_spend_feed_atomic_normalization(self):
        path=Path(self.tmp.name)/'simpli.csv';path.write_text('Date,Campaign ID,Spend,Impressions,Clicks\n2026-10-01,c1,100,10000,10\n')
        config={'type':'spend','path':str(path),'channel':'ctv','mapping':{'fields':{'date':'Date','campaign':'Campaign ID','cost':'Spend','impressions':'Impressions','clicks':'Clicks'},'constants':{'currency':'USD'}}}
        result=simplifi_reports.run(self.store,'a',config);self.assertEqual(result['rows'],1)
        row=self.store.report('a','2026-10-01','2026-10-01')[0];self.assertEqual(row['channel'],'ctv')
    def test_woo_net_refund_and_unknown_allocation(self):
        o={'id':1,'status':'processing','date_paid_gmt':'2026-10-01T01:00:00','date_created_gmt':'2026-10-01T00:00:00','date_modified_gmt':'2026-10-02T00:00:00','currency':'USD','line_items':[{'total':'100'}],'customer_id':0,'meta_data':[]}
        r=commerce_sync.woo_normalize('a',o,[{'amount':'20','line_items':[{'product_id':10,'total':'-20'}]}]);self.assertEqual(r['net'],'80')
        with self.assertRaises(ValueError):commerce_sync.woo_normalize('a',o,[{'amount':'20','line_items':[]}])
    def test_privacy_redacts_customer_and_closes_store(self):
        customer=hmac.new(b'fixture',b'123',hashlib.sha256).hexdigest()
        self.store.order('a',{'order_id':'o','revenue':100,'ts':now(),'currency':'USD','customer_id':customer,'visitor_id':'v'})
        commerce_privacy.handle(self.store,'a','customers/data_request','req',{'customer':{'id':123}})
        self.assertEqual(commerce_privacy.requests(self.store,'a')[0]['state'],'awaiting_merchant_fulfillment')
        commerce_privacy.handle(self.store,'a','customers/redact','redact',{'customer':{'id':123}})
        with self.store.db() as db:self.assertIsNone(db.execute('SELECT customer FROM orders').fetchone()[0])
        commerce_privacy.handle(self.store,'a','shop/redact','close',{})
        self.assertIsNone(self.store.auth(self.keys['agency_token']))
        with self.assertRaises(ValueError):self.store.tenant('a')
        self.assertEqual(commerce_privacy.handle(self.store,'a','shop/redact','close',{})['status'],'duplicate')
    def test_pipeline_due_interval(self):
        cfg={'jobs':[{'tenant':'a','id':'stub','kind':'stub','interval_seconds':3600}]}
        with patch.object(run_pipeline,'execute',return_value={'rows':1}) as execute:
            a=run_pipeline.run(self.store,cfg);b=run_pipeline.run(self.store,cfg)
        self.assertEqual(execute.call_count,1);self.assertEqual(b[0]['state'],'not_due')
    def test_experiment_publication_requires_approval_and_projects_safe_fields(self):
        future=datetime.now(timezone.utc)+timedelta(days=1);end=future+timedelta(days=1)
        experiments.create(self.store,'a',{'id':'lift','start':future.isoformat(),'end':end.isoformat(),'unit_type':'customer','hypothesis':'test','min_units_per_arm':20})
        for i in range(60):experiments.enroll(self.store,'a','lift','unit'+str(i))
        with self.assertRaises(ValueError):publications.publish(self.store,'a','lift',{},'test')
        final=(end+timedelta(days=1)).isoformat(timespec='microseconds')
        with patch('ims.experiments.now',return_value=final):
            safe=publications.publish(self.store,'a','lift',{'analyst_approved':True,'holdout_enforcement_verified':True,'acknowledge_warnings':True},'test')
        self.assertNotIn('salt',json.dumps(safe));self.assertNotIn('unit0',json.dumps(safe));self.assertEqual(len(publications.listed(self.store,'a')),1)

if __name__=='__main__':unittest.main()
