"""Shopify signed privacy webhooks; merchant export approval stays agency-only."""
import hashlib
import hmac
import json
from .core import ident,now
from .privacy import withdraw

def handle(store,tenant,topic,delivery,data):
    t=store.tenant(tenant,allow_closed=topic=='shop/redact')
    customer=str((data.get('customer') or {}).get('id') or '')
    pseudonym=hmac.new(t['shop_secret'].encode(),customer.encode(),hashlib.sha256).hexdigest() if customer else None
    with store.db() as db:
        if db.execute('SELECT 1 FROM privacy_requests WHERE tenant=? AND id=?',(tenant,delivery)).fetchone():
            return {'status':'duplicate'}
        orders=[dict(r) for r in db.execute('SELECT order_id,visitor,customer,currency,gross,ts FROM orders WHERE tenant=? AND customer=?',(tenant,pseudonym))] if pseudonym else []
    if topic=='customers/data_request':
        safe={'orders':[{'order_id':r['order_id'],'currency':r['currency'],'gross_minor_units':r['gross'],'timestamp':r['ts']} for r in orders],
              'note':'Minimal held order data. Agency must fulfill the merchant data request; no customer email/phone stored.'}
        state='awaiting_merchant_fulfillment'
    elif topic=='customers/redact':
        visitors={r['visitor'] for r in orders if r['visitor']}
        with store.db() as db:
            for o in orders:
                visitors.update(r['visitor'] for r in db.execute('SELECT visitor FROM observations WHERE tenant=? AND order_id=?',(tenant,o['order_id'])))
        for visitor in visitors:withdraw(store,tenant,visitor,True,'shopify-privacy')
        with store.db() as db:
            for o in orders:
                db.execute('DELETE FROM ctv_order_networks WHERE tenant=? AND order_id=?',(tenant,o['order_id']))
                db.execute('UPDATE orders SET customer=NULL,visitor=NULL WHERE tenant=? AND order_id=?',(tenant,o['order_id']))
                # Local experiment records linked by this order ID are removed; snapshots
                # are unpublished for analyst review. No claim of external vendor erasure.
                experiments=[r['experiment'] for r in db.execute('SELECT experiment FROM outcomes WHERE tenant=? AND outcome=?',(tenant,o['order_id']))]
                db.execute('DELETE FROM outcomes WHERE tenant=? AND outcome=?',(tenant,o['order_id']))
                for exp in experiments:db.execute('DELETE FROM experiment_publications WHERE tenant=? AND experiment=?',(tenant,exp))
            store.audit(db,tenant,'shopify-privacy','customer.redact',{'orders':len(orders)})
        safe={'orders_anonymized':len(orders),'external_vendor_erasure':'merchant/operator must follow provider deletion process'};state='local_redaction_completed'
    elif topic=='shop/redact':
        with store.db() as db:
            # Persist receipt only; purge operational tenant data and revoke all reporting keys.
            db.execute('PRAGMA defer_foreign_keys=ON')
            tables=[r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                columns={r['name'] for r in db.execute('PRAGMA table_info("'+table+'")')}
                if 'tenant' in columns and table!='privacy_requests':db.execute('DELETE FROM "'+table+'" WHERE tenant=?',(tenant,))
            db.execute('DELETE FROM privacy_requests WHERE tenant=?',(tenant,))
            db.execute('INSERT INTO tenant_shutdown VALUES(?,?)',(tenant,now()))
            # Keep minimal shop domain/HMAC configuration for authenticating retried redaction
            # requests. Operator removes tenant/secret after provider retry window.
        safe={'status':'local_shop_data_purged','note':'Remove retained webhook verification secret after retry period; revoke external account access.'};state='local_redaction_completed'
    else:raise ValueError('Unsupported privacy topic')
    with store.db() as db:
        db.execute('INSERT OR IGNORE INTO privacy_requests VALUES(?,?,?,?,?,?)',(tenant,ident(delivery),topic,now(),state,json.dumps(safe)))
    return {'status':state}

def requests(store,tenant):
    with store.db() as db:return [dict(r) for r in db.execute('SELECT id,topic,created,state,body FROM privacy_requests WHERE tenant=? ORDER BY created DESC LIMIT 100',(tenant,))]
