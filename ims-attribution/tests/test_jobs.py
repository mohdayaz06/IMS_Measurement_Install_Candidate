import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ims.core import Store

def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parent.parent/'integrations'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class JobTests(unittest.TestCase):
    def test_google_maps_cost_and_campaign(self):
        m=load('spend_sync')
        response=[{'results':[{'segments':{'date':'2026-10-01'},'campaign':{'id':'123'},'customer':{'currencyCode':'USD'},'metrics':{'costMicros':'123450000','clicks':'15','impressions':'1000'}}]}]
        with patch.dict(os.environ,{'GOOGLE_ADS_ACCESS_TOKEN':'fake','GOOGLE_ADS_DEVELOPER_TOKEN':'fake','GOOGLE_ADS_API_VERSION':'vXX','GOOGLE_ADS_CUSTOMER_ID':'123'}),patch.object(m,'request',return_value=response):
            r=list(m.google('2026-10-01','2026-10-01'))[0]
        self.assertEqual(r['campaign'],'123');self.assertEqual(r['cost'],'123.45')
    def test_meta_paging(self):
        m=load('spend_sync');r={'date_start':'2026-10-01','campaign_id':'7','account_currency':'USD','spend':'4'}
        pages=[{'data':[r],'paging':{'next':'https://untrusted.example/','cursors':{'after':'next'}}},{'data':[r]}]
        with patch.dict(os.environ,{'META_API_VERSION':'vXX','META_AD_ACCOUNT_ID':'act_123','META_ACCESS_TOKEN':'fake'}),patch.object(m,'request',side_effect=pages) as request:
            rows=list(m.meta('2026-10-01','2026-10-01'))
        self.assertEqual(len(rows),2);self.assertTrue(request.call_args_list[1].args[0].startswith('https://graph.facebook.com/'))
    def test_outbox_requires_verified_order_and_marketing_consent(self):
        m=load('deliver_conversions')
        with tempfile.TemporaryDirectory() as d:
            s=Store(d+'/db');s.create_tenant('a')
            order={'order_id':'o','ts':'2026-10-01T00:00:00Z','currency':'USD','revenue':100}
            s.order('a',order)
            event={'event_id':'e','visitor_id':'v','order_id':'o','analytics_consent':True,'marketing_consent':False}
            s.touch('a',event);m.enqueue(s)
            with s.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
            s.touch('a',{**event,'event_id':'e2','marketing_consent':True});m.enqueue(s);m.enqueue(s)
            with s.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
    def test_export_field_allowlist_excludes_vendor_cost(self):
        m=load('export_bigquery')
        self.assertNotIn('vendor_cost',m.SAFE);self.assertNotIn('agency_gross_profit',m.SAFE)
        self.assertIn('media_cost',m.SAFE)

if __name__=='__main__':unittest.main()
