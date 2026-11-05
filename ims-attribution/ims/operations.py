"""Local backup, scoped key issuance and safe operational status."""
import os
import secrets
import sqlite3
from pathlib import Path
from .core import digest,ident,now

def issue_key(store,tenant,role,label):
    store.tenant(tenant)
    if role not in {'agency','client'}:raise ValueError('Unsupported role')
    token=secrets.token_urlsafe(32)
    with store.db() as db:
        db.execute('INSERT INTO keys VALUES(?,?,?,?,?,0)',(digest(token),tenant,role,str(label)[:80],now()))
        store.audit(db,tenant,'operator','key.issue',{'role':role,'label':str(label)[:80]})
    return {'token':token,'fingerprint':digest(token),'role':role,'tenant':tenant}

def backup(store,destination):
    path=Path(destination)
    if not path.is_absolute() or path.resolve()==Path(store.path).resolve():raise ValueError('Use distinct absolute backup path')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise ValueError('Backup must not overwrite an existing file')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    try:
        with sqlite3.connect(store.path) as source,sqlite3.connect(path) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed')
    except Exception:
        path.unlink(missing_ok=True);raise
    return {'status':'backed_up','bytes':path.stat().st_size}

def status(store,tenant):
    store.tenant(tenant)
    with store.db() as db:
        touch=db.execute('SELECT MAX(ts) FROM touches WHERE tenant=?',(tenant,)).fetchone()[0]
        order=db.execute('SELECT MAX(ts) FROM orders WHERE tenant=?',(tenant,)).fetchone()[0]
        spend=db.execute('SELECT MAX(day) FROM spend WHERE tenant=?',(tenant,)).fetchone()[0]
        jobs=[dict(r) for r in db.execute('SELECT job,started,finished,state FROM job_runs j WHERE tenant=? AND id=(SELECT MAX(id) FROM job_runs x WHERE x.tenant=j.tenant AND x.job=j.job)',(tenant,))]
        outbox={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM outbox WHERE tenant=? GROUP BY state',(tenant,))}
        destinations={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM destination_deliveries WHERE tenant=? GROUP BY state',(tenant,))}
    return {'last_observed_touch':touch,'last_order_time':order,'latest_spend_date':spend,'jobs':jobs,'gateway_delivery_states':outbox,'native_delivery_states':destinations,
            'note':'Timestamp freshness is observation time/date, not proof of a complete vendor sync. Gateway acceptance is not platform attribution.'}
