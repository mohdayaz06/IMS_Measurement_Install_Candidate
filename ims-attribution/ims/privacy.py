"""Trusted merchant/CMP server must authorize withdrawal requests; not a public ID API."""
from .core import ident,now

def withdraw(store,tenant,visitor,erase_analytics=False,actor='agency'):
    visitor=ident(visitor);scope='analytics' if erase_analytics else 'marketing'
    with store.db() as db:
        old=db.execute('SELECT scope FROM consent_blocks WHERE tenant=? AND visitor=?',(tenant,visitor)).fetchone()
        if old and old['scope']=='analytics':scope='analytics'
        db.execute('INSERT INTO consent_blocks VALUES(?,?,?,?) ON CONFLICT(tenant,visitor) DO UPDATE SET scope=excluded.scope,ts=excluded.ts',(tenant,visitor,scope,now()))
        db.execute('DELETE FROM signals WHERE tenant=? AND visitor=?',(tenant,visitor))
        db.execute("UPDATE outbox SET state='consent_blocked' WHERE tenant=? AND state='pending' AND order_id IN (SELECT order_id FROM observations WHERE tenant=? AND visitor=?)",(tenant,tenant,visitor))
        db.execute('UPDATE observations SET marketing=0 WHERE tenant=? AND visitor=?',(tenant,visitor))
        db.execute("UPDATE destination_deliveries SET state='consent_blocked' WHERE tenant=? AND state IN ('pending','awaiting_identifier') AND order_id IN (SELECT order_id FROM observations WHERE tenant=? AND visitor=?)",(tenant,tenant,visitor))
        if scope=='analytics':
            db.execute('DELETE FROM ctv_order_networks WHERE tenant=? AND order_id IN (SELECT order_id FROM observations WHERE tenant=? AND visitor=? UNION SELECT order_id FROM orders WHERE tenant=? AND visitor=?)',(tenant,tenant,visitor,tenant,visitor))
            db.execute('DELETE FROM touches WHERE tenant=? AND visitor=?',(tenant,visitor))
            db.execute('DELETE FROM observations WHERE tenant=? AND visitor=?',(tenant,visitor))
            db.execute('UPDATE orders SET visitor=NULL WHERE tenant=? AND visitor=?',(tenant,visitor))
        # Audit is operation/count only, not a duplicate identifying record.
        store.audit(db,tenant,actor,'consent.withdraw',{'scope':scope})
    return {'status':'withdrawn','scope':scope,'note':'Future unsent forwarding blocked; completed vendor deliveries require provider-side deletion/withdrawal workflow.'}

def fresh_grant(store,tenant,visitor,actor='agency'):
    visitor=ident(visitor)
    with store.db() as db:
        db.execute('DELETE FROM consent_blocks WHERE tenant=? AND visitor=?',(tenant,visitor))
        store.audit(db,tenant,actor,'consent.fresh_grant',{})
    return {'status':'fresh_grant_recorded','note':'No historical data restored. Only use after independently verifying a new consent decision.'}
