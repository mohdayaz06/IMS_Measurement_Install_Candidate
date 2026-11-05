"""Read-only WooCommerce and BigCommerce order/refund adapters.
Signed vendor callbacks are optional: scheduled authoritative API reads do not trust
browser revenue. All sources use one net merchandise policy; ambiguous refunds fail.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime,timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode,urlsplit
from ims.core import Store,stamp
from .http_client import call

def pseudonym(tenant,value):
    if not value:return None
    secret=os.environ.get('IMS_CUSTOMER_HMAC_KEY','')
    if len(secret)<32:raise ValueError('Set IMS_CUSTOMER_HMAC_KEY with >=32 random characters')
    return hmac.new(secret.encode(),(tenant+':'+str(value)).encode(),hashlib.sha256).hexdigest()

def apply(store,tenant,order):
    t=store.tenant(tenant)
    if order['currency']!=t['currency']:raise ValueError('Store currency mismatch')
    with store.db() as db:
        exists=db.execute('SELECT 1 FROM orders WHERE tenant=? AND order_id=?',(tenant,order['order_id'])).fetchone()
        if not exists:
            store.order(tenant,{k:v for k,v in order.items() if k not in {'net','updated'}},db)
        store.order_snapshot(tenant,order['order_id'],order['net'],order['updated'],source=order['source'],db=db)
        store.audit(db,tenant,'commerce-sync','order.reconcile',{'source':order['source']})

def woo_normalize(tenant,o,refunds):
    if o['status'] not in {'processing','completed','refunded'} or not o.get('date_paid_gmt'):
        return None
    gross=sum((Decimal(str(line['total'])) for line in o.get('line_items',[])),Decimal(0))
    returned=Decimal(0)
    for refund in refunds:
        lines=refund.get('line_items',[])
        merchandise=sum((abs(Decimal(str(line['total']))) for line in lines if line.get('product_id')),Decimal(0))
        # A refund with no explicit merchandise allocation cannot be silently classified.
        if not lines and Decimal(str(refund.get('amount','0')))>0:
            raise ValueError('WooCommerce amount-only refund requires merchandise allocation')
        returned+=merchandise
    attrs={m['key']:m['value'] for m in o.get('meta_data',[])}
    created=o['date_created_gmt'];updated=o.get('date_modified_gmt') or created
    return {'order_id':str(o['id']),'visitor_id':attrs.get('_ims_visitor_id'),
        'ts':stamp(created+'Z' if '+' not in created and not created.endswith('Z') else created),
        'updated':stamp(updated+'Z' if '+' not in updated and not updated.endswith('Z') else updated),
        'currency':o['currency'],'revenue':str(gross),'net':str(max(Decimal(0),gross-returned)),
        'customer_id':pseudonym(tenant,o.get('customer_id')),'source':'woocommerce_api'}

def woo_sync(store,tenant,base_url,since,key,secret):
    u=urlsplit(base_url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError('Fixed HTTPS WooCommerce origin required')
    auth=base64.b64encode((key+':'+secret).encode()).decode();headers={'Authorization':'Basic '+auth}
    base=base_url.rstrip('/')+'/wp-json/wc/v3';page=1;count=0
    while True:
        params={'modified_after':stamp(since).replace('+00:00','Z'),'dates_are_gmt':'true','per_page':100,'page':page}
        orders=call(base+'/orders?'+urlencode(params),headers)
        if not isinstance(orders,list):raise ValueError('Unexpected WooCommerce response')
        for order in orders:
            refunds=[];rp=1
            if order.get('refunds'):
                while True:
                    chunk=call(base+'/orders/'+str(int(order['id']))+'/refunds?per_page=100&page='+str(rp),headers)
                    if not isinstance(chunk,list):raise ValueError('Unexpected refund response')
                    refunds.extend(chunk)
                    if len(chunk)<100:break
                    rp+=1
            normalized=woo_normalize(tenant,order,refunds)
            if normalized:apply(store,tenant,normalized);count+=1
        if len(orders)<100:break
        page+=1
    return {'orders_reconciled':count}

def bc_normalize(tenant,o,paid_status_ids):
    # Payment statuses vary by gateway; paid order-status mapping must be merchant approved.
    if int(o['status_id']) not in paid_status_ids:return None
    gross=Decimal(str(o['subtotal_ex_tax']))-Decimal(str(o.get('discount_amount','0')))
    refund=Decimal(str(o.get('refunded_amount','0')))
    # V2 refunded_amount can mix shipping/tax. Do not pretend it is merchandise-only.
    if refund>0:raise ValueError('BigCommerce refunded order needs item-level refund allocation feed')
    def date(value):
        try:return stamp(value)
        except ValueError:return stamp(parsedate_to_datetime(value).isoformat())
    return {'order_id':str(o['id']),'visitor_id':None,'ts':date(o['date_created']),
        'updated':date(o.get('date_modified') or o['date_created']),'currency':o['currency_code'],
        'revenue':str(max(Decimal(0),gross)),'net':str(max(Decimal(0),gross)),
        'customer_id':pseudonym(tenant,o.get('customer_id')),'source':'bigcommerce_api'}

def bigcommerce_sync(store,tenant,store_hash,since,token,paid_status_ids):
    if not re.fullmatch(r'[a-z0-9]+',store_hash) or not paid_status_ids:raise ValueError('Store hash and approved paid statuses required')
    base='https://api.bigcommerce.com/stores/'+store_hash+'/v2/orders';page=1;count=0
    while True:
        params={'min_date_modified':stamp(since),'limit':100,'page':page}
        orders=call(base+'?'+urlencode(params),{'X-Auth-Token':token,'Accept':'application/json'})
        if not isinstance(orders,list):raise ValueError('Unexpected BigCommerce response')
        for o in orders:
            normalized=bc_normalize(tenant,o,paid_status_ids)
            if normalized:apply(store,tenant,normalized);count+=1
        if len(orders)<100:break
        page+=1
    return {'orders_reconciled':count}

def main():
    p=argparse.ArgumentParser();p.add_argument('platform',choices=['woocommerce','bigcommerce']);p.add_argument('--tenant',required=True);p.add_argument('--since',required=True);a=p.parse_args();store=Store(os.environ['IMS_DB'])
    if a.platform=='woocommerce':r=woo_sync(store,a.tenant,os.environ['WOO_BASE_URL'],a.since,os.environ['WOO_CONSUMER_KEY'],os.environ['WOO_CONSUMER_SECRET'])
    else:r=bigcommerce_sync(store,a.tenant,os.environ['BC_STORE_HASH'],a.since,os.environ['BC_ACCESS_TOKEN'],[int(x) for x in os.environ['BC_PAID_STATUS_IDS'].split(',')])
    print(json.dumps(r))
if __name__=='__main__':main()
