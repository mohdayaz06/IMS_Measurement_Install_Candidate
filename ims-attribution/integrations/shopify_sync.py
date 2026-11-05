"""GraphQL historical/rolling order reconciliation. Does not collect IP by default.
Current net merchandise subtotal is an authoritative snapshot; prior refunds aren't
subtracted twice. Permissions/API version must be verified against merchant account.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import urllib.request
from datetime import datetime
from ims.core import Store,stamp,now

QUERY='''query IMSOrders($after:String,$search:String!){
  orders(first:50,after:$after,query:$search,sortKey:UPDATED_AT){
    pageInfo{hasNextPage endCursor}
    nodes{id legacyResourceId createdAt updatedAt test displayFinancialStatus currencyCode
      subtotalPriceSet{shopMoney{amount currencyCode}}
      currentSubtotalPriceSet{shopMoney{amount currencyCode}}
      customer{legacyResourceId}
      customAttributes{key value}
    }
  }
}'''

def graphql(shop,version,token,variables):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com',shop):raise ValueError('Invalid Shopify domain')
    if not re.fullmatch(r'20\d{2}-(01|04|07|10)',version):raise ValueError('Pin supported stable Shopify API version')
    raw=json.dumps({'query':QUERY,'variables':variables}).encode()
    req=urllib.request.Request('https://'+shop+'/admin/api/'+version+'/graphql.json',data=raw,
        headers={'Content-Type':'application/json','X-Shopify-Access-Token':token})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=45) as response:data=json.load(response)
    if data.get('errors'):raise RuntimeError('Shopify GraphQL error; verify scope/schema/throttling')
    return data['data']['orders']

def apply_page(store,tenant,nodes):
    t=store.tenant(tenant);applied=0
    with store.db() as db:
        for o in nodes:
            if o.get('test') or o['displayFinancialStatus'] not in {'PAID','PARTIALLY_REFUNDED','REFUNDED'}:continue
            original=o['subtotalPriceSet']['shopMoney'];current=o['currentSubtotalPriceSet']['shopMoney']
            if original['currencyCode']!=t['currency'] or current['currencyCode']!=t['currency'] or o['currencyCode']!=t['currency']:
                raise ValueError('Shop currency mismatch')
            oid=str(o['legacyResourceId']);attrs={a['key']:a['value'] for a in o.get('customAttributes',[])}
            exists=db.execute('SELECT 1 FROM orders WHERE tenant=? AND order_id=?',(tenant,oid)).fetchone()
            if not exists:
                customer=str((o.get('customer') or {}).get('legacyResourceId') or '')
                if customer and not t['shop_secret']:raise ValueError('Customer pseudonym secret required')
                pseudonym=hmac.new(t['shop_secret'].encode(),customer.encode(),hashlib.sha256).hexdigest() if customer else None
                store.order(tenant,{'order_id':oid,'visitor_id':attrs.get('ims_visitor_id'),'ts':o['createdAt'],
                    'currency':t['currency'],'revenue':original['amount'],'customer_id':pseudonym,'source':'shopify_reconciled'},db)
            store.order_snapshot(tenant,oid,current['amount'],o['updatedAt'],db=db)
            applied+=1
        store.audit(db,tenant,'shopify-sync','orders.reconcile',{'processed':len(nodes),'applied':applied})
    return applied

def sync(store,tenant,since,version,token):
    start=stamp(since);t=store.tenant(tenant);cursor=None;count=0
    while True:
        page=graphql(t['shop'],version,token,{'after':cursor,'search':'updated_at:>='+start})
        count+=apply_page(store,tenant,page['nodes'])
        info=page['pageInfo']
        if not info['hasNextPage']:break
        if not info['endCursor'] or info['endCursor']==cursor:raise RuntimeError('Invalid pagination cursor')
        cursor=info['endCursor']
    return {'orders_reconciled':count}

def main():
    p=argparse.ArgumentParser();p.add_argument('--tenant',required=True);p.add_argument('--since',required=True);a=p.parse_args()
    result=sync(Store(os.environ['IMS_DB']),a.tenant,a.since,os.environ['SHOPIFY_API_VERSION'],os.environ['SHOPIFY_ADMIN_ACCESS_TOKEN'])
    print(json.dumps(result))
if __name__=='__main__':main()
