"""Agency-only retry controls; never automatically replay accepted production events."""
from .core import ident,now

def retry(store,tenant,data,actor):
    kind=data.get('kind','native')
    if kind not in {'native','sgtm'}:raise ValueError('Unknown delivery kind')
    order=ident(data['order_id']);reason=str(data.get('reason','')).strip()
    if len(reason)<5:raise ValueError('Operator reason required')
    with store.db() as db:
        if kind=='native':
            destination=ident(data['destination'])
            row=db.execute('SELECT state FROM destination_deliveries WHERE tenant=? AND order_id=? AND destination=?',(tenant,order,destination)).fetchone()
            if not row or row['state'] not in {'configuration_error','dead_letter','validated_only','test_received','awaiting_identifier'}:
                raise ValueError('Only failed/test/identifier-waiting native deliveries may be reset')
            db.execute("UPDATE destination_deliveries SET state='pending',attempts=0,next_attempt=?,last_status=NULL WHERE tenant=? AND order_id=? AND destination=?",(now(),tenant,order,destination))
        else:
            row=db.execute('SELECT state FROM outbox WHERE tenant=? AND order_id=?',(tenant,order)).fetchone()
            if not row or row['state']!='dead_letter':raise ValueError('Only dead-letter gateway deliveries may be reset')
            db.execute("UPDATE outbox SET state='pending',attempts=0,next_attempt=?,last_status=NULL WHERE tenant=? AND order_id=?",(now(),tenant,order))
        store.audit(db,tenant,actor,'delivery.retry',{'kind':kind,'reason':reason[:500]})
    return {'status':'pending','note':'Consent and age checks still apply; stable event ID is retained.'}
