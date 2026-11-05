import os
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from ims.core import Store
from ims import ctv
from ims import experiments

class CTVTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name+'/db');self.s.create_tenant('a');self.s.create_tenant('b')
        self.env=patch.dict(os.environ,{'IMS_IP_HMAC_KEY':'test-key-only-'+'x'*40});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def order(self):self.s.order('a',{'order_id':'o','ts':'2026-10-10T12:00:00Z','currency':'USD','revenue':200})
    def impression(self,id='i',ts='2026-10-09T12:00:00Z',campaign='CTV1',ip='8.8.8.8'):
        # Public-address fixture is synthetic; no claim this public resolver is residential.
        return {'impression_id':id,'ts':ts,'campaign':campaign,'provider':'fixture','ip_address':ip,'measurement_permitted':True}
    def link(self):ctv.link_orders(self.s,'a',[{'order_id':'o','ip_address':'8.8.8.8','measurement_permitted':True}])
    def test_tenant_keys_differ_ipv4mapped_normalizes(self):
        self.assertNotEqual(ctv.network_key('a','8.8.8.8'),ctv.network_key('b','8.8.8.8'))
        self.assertEqual(ctv.network_key('a','8.8.8.8'),ctv.network_key('a','::ffff:8.8.8.8'))
        with self.assertRaises(ValueError):ctv.network_key('a','192.168.1.1')
    def test_match_dedup_last_impression_and_no_raw_ip(self):
        self.order();self.link();a=self.impression();b=self.impression('i2','2026-10-10T10:00:00Z','CTV2')
        ctv.impressions(self.s,'a',[a,b]);ctv.impressions(self.s,'a',[a,b])
        r=ctv.report(self.s,'a','2026-10-01','2026-10-31')
        self.assertEqual(r['associated_orders'],1);self.assertEqual(r['rows'][0]['campaign'],'CTV2')
        with self.s.db() as db:
            data=str([tuple(x) for x in db.execute('SELECT * FROM ctv_impressions')])
        self.assertNotIn('8.8.8.8',data)
    def test_future_and_expired_impressions_not_matched(self):
        self.order();self.link()
        ctv.impressions(self.s,'a',[self.impression('old','2026-10-01T00:00:00Z'),self.impression('after','2026-10-11T00:00:00Z')])
        self.assertEqual(ctv.report(self.s,'a','2026-10-01','2026-10-31',24)['associated_orders'],0)
    def test_cannot_create_sale_from_ctv_ip(self):
        with self.assertRaises(ValueError):self.link()
    def test_denied_or_known_proxy_rejected(self):
        with self.assertRaises(ValueError):ctv.impressions(self.s,'a',[{**self.impression(),'measurement_permitted':False}])
        with self.assertRaises(ValueError):ctv.impressions(self.s,'a',[{**self.impression(),'network_type':'ssai_server'}])
    def test_ctv_metrics_use_billable_cost(self):
        self.order();self.link();ctv.impressions(self.s,'a',[self.impression()])
        self.s.spend('a',[{'date':'2026-10-09','channel':'ctv','campaign':'CTV1','currency':'USD','cost':50,'impressions':1000,'clicks':0}]);self.s.markup('a','*','2026-01-01',10000)
        r=ctv.report(self.s,'a','2026-10-01','2026-10-31')['rows'][0]
        self.assertEqual(r['media_cost'],100);self.assertEqual(r['associated_roas'],2);self.assertNotIn('vendor_cost',r)
    def test_incrementality_counts_control_orders_without_impressions(self):
        start=datetime.now(timezone.utc)+timedelta(days=2);end=start+timedelta(days=7)
        experiments.create(self.s,'a',{'id':'ctv-lift','start':start.isoformat(),'end':end.isoformat(),'unit_type':'household_ip','hypothesis':'CTV increases household revenue','min_units_per_arm':20})
        arms=set()
        for i in range(80):
            ip='11.0.0.'+str(i+1)
            unit=ctv.enroll_ip(self.s,'a','ctv-lift',{'ip_address':ip,'measurement_permitted':True})
            arms.add(unit['arm'])
            order={'order_id':'x'+str(i),'ts':(start+timedelta(days=1)).isoformat(),'currency':'USD','revenue':20 if unit['arm']=='treatment' else 10}
            self.s.order('a',order)
            ctv.link_orders(self.s,'a',[{'order_id':order['order_id'],'ip_address':ip,'measurement_permitted':True}])
        self.assertEqual(arms,{'treatment','control'})
        with patch('ims.experiments.now',return_value=(end+timedelta(days=1)).isoformat(timespec='microseconds')):
            synced=ctv.sync_outcomes(self.s,'a','ctv-lift')
            self.assertEqual(synced['orders'],80)
            report=experiments.analyze(self.s,'a','ctv-lift',iterations=100)
            self.assertEqual(report['revenue_per_control_unit'],10)
            self.assertEqual(report['revenue_lift_per_unit'],10)
            # A later merchandise refund restates independent outcomes, not a second sale.
            self.s.refund('a',{'refund_id':'refund-x0','order_id':'x0','amount':5,'ts':(start+timedelta(hours=30)).isoformat()})
            ctv.sync_outcomes(self.s,'a','ctv-lift')
            with self.s.db() as db:
                revised=db.execute("SELECT revenue FROM outcomes WHERE tenant='a' AND experiment='ctv-lift' AND outcome='x0'").fetchone()[0]
                expected=db.execute("SELECT net FROM ledger_net WHERE tenant='a' AND order_id='x0'").fetchone()[0]
            self.assertEqual(revised,expected)

if __name__=='__main__':unittest.main()
