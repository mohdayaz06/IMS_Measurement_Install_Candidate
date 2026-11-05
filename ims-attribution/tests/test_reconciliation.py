import tempfile
import unittest
from ims.core import Store
from integrations.shopify_sync import apply_page

class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name+'/db');self.s.create_tenant('a',shop='a.myshopify.com',shop_secret='fixture')
    def tearDown(self):self.tmp.cleanup()
    def node(self,current='80',updated='2026-10-12T00:00:00Z'):
        return {'legacyResourceId':'1','createdAt':'2026-10-01T00:00:00Z','updatedAt':updated,'test':False,
                'displayFinancialStatus':'PARTIALLY_REFUNDED','currencyCode':'USD','customer':None,'customAttributes':[],
                'subtotalPriceSet':{'shopMoney':{'amount':'100','currencyCode':'USD'}},
                'currentSubtotalPriceSet':{'shopMoney':{'amount':current,'currencyCode':'USD'}}}
    def revenue(self):return sum(r['revenue'] for r in self.s.report('a','2026-10-01','2026-10-31'))
    def test_snapshot_does_not_double_subtract_prior_refund(self):
        self.s.refund('a',{'refund_id':'r','order_id':'1','amount':20,'ts':'2026-10-11T00:00:00Z'})
        apply_page(self.s,'a',[self.node()]);apply_page(self.s,'a',[self.node()])
        self.assertEqual(self.revenue(),80)
    def test_later_refund_applied_until_next_snapshot(self):
        apply_page(self.s,'a',[self.node()])
        self.s.refund('a',{'refund_id':'r','order_id':'1','amount':10,'ts':'2026-10-13T00:00:00Z'})
        self.assertEqual(self.revenue(),70)
        apply_page(self.s,'a',[self.node('70','2026-10-14T00:00:00Z')])
        self.assertEqual(self.revenue(),70)
    def test_stale_snapshot_ignored_conflicting_version_rejected(self):
        apply_page(self.s,'a',[self.node()]);apply_page(self.s,'a',[self.node('100','2026-10-10T00:00:00Z')])
        self.assertEqual(self.revenue(),80)
        with self.assertRaises(ValueError):apply_page(self.s,'a',[self.node('99')])
    def test_order_edit_changes_report_without_second_purchase(self):
        apply_page(self.s,'a',[self.node('150')])
        report=self.s.report('a','2026-10-01','2026-10-31')
        self.assertEqual(sum(r['orders'] for r in report),1);self.assertEqual(self.revenue(),150)
    def test_test_orders_excluded(self):
        apply_page(self.s,'a',[{**self.node(),'test':True}]);self.assertEqual(self.revenue(),0)

if __name__=='__main__':unittest.main()
