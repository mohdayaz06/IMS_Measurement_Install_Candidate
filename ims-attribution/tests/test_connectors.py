import hashlib
import hmac
import io
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from ims.core import Store
from ims import connectors,privacy,operations
from ims.app import make_app
from integrations.universal_csv import payload_from_csv
from integrations import run_pipeline

class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name+'/db');self.s.create_tenant('a')
        r=connectors.register(self.s,'a',{'id':'vendor','platform':'new_dsp','account':'account1','currency':'USD','timezone':'UTC','capabilities':['spend']})
        self.secret='test-only-'+'x'*40;self.secret_env=r['secret_environment_variable']
        self.env=patch.dict(os.environ,{self.secret_env:self.secret});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def signed(self,data,delivery='one',timestamp=None):
        raw=json.dumps(data).encode();ts=timestamp or str(int(time.time()))
        sig=hmac.new(self.secret.encode(),ts.encode()+b'.'+delivery.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return {'timestamp':ts,'delivery':delivery,'signature':sig},raw
    def data(self):return {'type':'spend','rows':[{'date':'2026-10-01','campaign':'123','currency':'USD','cost':'100','impressions':100,'clicks':1}]}
    def test_arbitrary_platform_signed_ingest_replay_account_namespace(self):
        h,raw=self.signed(self.data())
        self.assertEqual(connectors.ingest(self.s,'a','vendor',h,raw)['status'],'accepted')
        self.assertEqual(connectors.ingest(self.s,'a','vendor',h,raw)['status'],'duplicate')
        r=self.s.report('a','2026-10-01','2026-10-31')[0]
        self.assertEqual(r['channel'],'new_dsp');self.assertEqual(r['campaign'],'new_dsp:account1:123');self.assertEqual(r['media_cost'],100)
    def test_bad_signature_expired_and_forbidden_kind(self):
        h,raw=self.signed(self.data())
        with self.assertRaises(PermissionError):connectors.ingest(self.s,'a','vendor',{**h,'signature':'bad'},raw)
        h,raw=self.signed(self.data(),timestamp=str(int(time.time())-600))
        with self.assertRaises(PermissionError):connectors.ingest(self.s,'a','vendor',h,raw)
        h,raw=self.signed({'type':'orders','rows':[{}]})
        with self.assertRaises(PermissionError):connectors.ingest(self.s,'a','vendor',h,raw)
    def test_conflicting_replay_rejected(self):
        h,raw=self.signed(self.data());connectors.ingest(self.s,'a','vendor',h,raw)
        data=self.data();data['rows'][0]['cost']='200';h,raw=self.signed(data)
        with self.assertRaises(ValueError):connectors.ingest(self.s,'a','vendor',h,raw)
    def test_api_supports_signed_ingest_without_agency_bearer(self):
        h,raw=self.signed(self.data())
        env={'REQUEST_METHOD':'POST','PATH_INFO':'/ingest/a/vendor','QUERY_STRING':'','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),
             'HTTP_X_IMS_TIMESTAMP':h['timestamp'],'HTTP_X_IMS_DELIVERY':h['delivery'],'HTTP_X_IMS_SIGNATURE':h['signature']}
        status=[];result=b''.join(make_app(self.s)(env,lambda s,headers:status.append(s)))
        self.assertTrue(status[0].startswith('202'));self.assertEqual(json.loads(result)['status'],'accepted')
    def test_csv_fragments_aggregate_before_upsert(self):
        path=self.tmp.name+'/fragment.csv'
        with open(path,'w') as f:f.write('date,id,spend,imps,clicks\n2026-10-01,12,10.01,100,1\n2026-10-01,12,20.02,200,2\n')
        result=payload_from_csv(path,{'fields':{'date':'date','campaign':'id','cost':'spend','impressions':'imps','clicks':'clicks'},'constants':{'currency':'USD'}})
        self.assertEqual(len(result['rows']),1);self.assertEqual(result['rows'][0]['cost'],'30.03');self.assertEqual(result['rows'][0]['clicks'],3)
    def test_withdrawal_blocks_future_marketing_even_if_browser_replays_grant(self):
        self.s.touch('a',{'event_id':'e1','visitor_id':'v','analytics_consent':True,'marketing_consent':True,'signals':{'gclid':'123'}})
        privacy.withdraw(self.s,'a','v')
        self.s.touch('a',{'event_id':'e2','visitor_id':'v','analytics_consent':True,'marketing_consent':True,'signals':{'gclid':'456'}})
        with self.s.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM signals').fetchone()[0],0)
        privacy.withdraw(self.s,'a','v',erase_analytics=True)
        self.assertEqual(self.s.touch('a',{'event_id':'e3','visitor_id':'v','analytics_consent':True})['status'],'consent_withdrawn')
    def test_backup_restore_integrity_and_reissued_keys(self):
        issued=operations.issue_key(self.s,'a','client','reporting')
        self.assertEqual(self.s.auth(issued['token'])['role'],'client')
        out=self.tmp.name+'/backup.db';operations.backup(self.s,out)
        restored=Store(out);self.assertEqual(restored.auth(issued['token'])['tenant'],'a')
        with self.assertRaises(ValueError):operations.backup(self.s,out)
    def test_pipeline_failure_skips_export_for_same_tenant(self):
        self.s.create_tenant('b')
        config={'jobs':[{'tenant':'a','id':'bad','kind':'unknown'},{'tenant':'a','id':'export','kind':'unknown'},{'tenant':'b','id':'other','kind':'unknown'}]}
        result=run_pipeline.run(self.s,config)
        self.assertEqual([r['state'] for r in result],['failed','skipped_due_to_prior_failure','failed'])
        status=operations.status(self.s,'a');self.assertEqual(status['jobs'][0]['state'],'failed')

if __name__=='__main__':unittest.main()
