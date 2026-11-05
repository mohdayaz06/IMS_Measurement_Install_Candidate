"""Platform-independent connector contract. No invented vendor endpoints."""
import hashlib
import hmac
import json
import os
import re
import time
from zoneinfo import ZoneInfo
from .core import ident,now,canonical_channel
from . import ctv

CAPABILITIES={'spend','orders','refunds','touches','ctv_impressions','order_networks'}

def register(store,tenant,data):
    t=store.tenant(tenant)
    cid=ident(data['id']);platform=canonical_channel(data['platform'],'paid')
    channel=canonical_channel(data.get('channel',platform),'paid')
    account=ident(data['account'])
    if data['currency']!=t['currency'] or data['timezone']!=t['timezone']:
        raise ValueError('Connector timezone/currency must match tenant; normalize upstream')
    ZoneInfo(data['timezone'])
    capabilities=set(data.get('capabilities',[]))
    if not capabilities or not capabilities<=CAPABILITIES:raise ValueError('Unsupported capability')
    fingerprint=hashlib.sha256((tenant+':'+cid).encode()).hexdigest()[:24].upper()
    secret_env='IMS_CONNECTOR_'+fingerprint
    with store.db() as db:
        db.execute('INSERT INTO connectors VALUES(?,?,?,?,?,?,?,?,?,1)',
                   (tenant,cid,platform,channel,account,data['currency'],data['timezone'],json.dumps(sorted(capabilities)),secret_env))
        store.audit(db,tenant,'agency','connector.register',{'id':cid,'platform':platform,'capabilities':sorted(capabilities)})
    return {'id':cid,'platform':platform,'secret_environment_variable':secret_env,
            'ingest_path':'/ingest/'+tenant+'/'+cid,
            'channel':channel,'campaign_key_prefix':platform+':'+account+':',
            'note':'Set a random >=32-character signing secret in the named server environment variable and in the trusted adapter. Do not expose it to browsers.'}

def catalog(store,tenant):
    with store.db() as db:
        rows=db.execute('SELECT id,platform,channel,account,currency,timezone,capabilities,enabled FROM connectors WHERE tenant=?',(tenant,)).fetchall()
    return [{**dict(r),'capabilities':json.loads(r['capabilities'])} for r in rows]

def ingest(store,tenant,cid,headers,raw):
    with store.db() as db:
        row=db.execute('SELECT * FROM connectors WHERE tenant=? AND id=? AND enabled=1',(tenant,cid)).fetchone()
    if not row:raise ValueError('Unknown or disabled connector')
    secret=os.environ.get(row['secret_env'],'')
    if len(secret)<32:raise ValueError('Connector signing secret not configured')
    timestamp=headers.get('timestamp','');delivery=ident(headers.get('delivery',''))
    try:seconds=int(timestamp)
    except ValueError:raise PermissionError('Invalid timestamp')
    if abs(time.time()-seconds)>300:raise PermissionError('Expired connector delivery')
    message=timestamp.encode()+b'.'+delivery.encode()+b'.'+raw
    signature=hmac.new(secret.encode(),message,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,headers.get('signature','')):
        raise PermissionError('Invalid connector signature')
    body_hash=hashlib.sha256(raw).hexdigest()
    with store.db() as db:
        old=db.execute('SELECT body_hash FROM connector_deliveries WHERE tenant=? AND connector=? AND delivery=?',(tenant,cid,delivery)).fetchone()
    if old:
        if old['body_hash']!=body_hash:raise ValueError('Conflicting connector replay')
        return {'status':'duplicate','delivery':delivery}
    data=json.loads(raw);kind=data['type'];rows=data['rows']
    if kind not in json.loads(row['capabilities']):raise PermissionError('Connector capability not authorized')
    if not isinstance(rows,list) or not 1<=len(rows)<=1000 or not all(isinstance(r,dict) for r in rows):
        raise ValueError('Expected 1–1000 canonical rows')
    # Prefixed campaign keys prevent account/platform collisions. SDK UTM campaign values
    # must use this same canonical key; native jobs are independent, unprefixed mode.
    normalized=[]
    prefix=row['platform']+':'+row['account']+':'
    for source in rows:
        r=dict(source)
        if 'campaign' in r:
            campaign=str(r['campaign'])
            if not campaign.startswith(prefix):campaign=prefix+campaign
            if len(campaign)>160:raise ValueError('Canonical campaign key too long')
            r['campaign']=campaign
        if kind=='spend':
            if r['currency']!=row['currency']:raise ValueError('Currency mismatch')
            r['channel']=row['channel']
        if kind=='touches':r['source']=row['channel'];r['medium']='paid'
        if kind=='ctv_impressions':r['provider']=row['platform']
        normalized.append(r)
    if kind=='spend':store.spend(tenant,normalized,'connector:'+cid)
    elif kind=='ctv_impressions':ctv.impressions(store,tenant,normalized)
    elif kind=='order_networks':ctv.link_orders(store,tenant,normalized)
    elif kind in {'orders','refunds'}:
        with store.db() as db:
            for r in normalized:(store.order if kind=='orders' else store.refund)(tenant,r,db)
    else:
        for r in normalized:store.touch(tenant,r,trusted=True)
    # Canonical tables are individually idempotent if a crash occurs before this receipt.
    # Partial batches are safe to retry but not claimed as distributed exactly-once writes.
    with store.db() as db:
        db.execute('INSERT OR IGNORE INTO connector_deliveries VALUES(?,?,?,?,?)',(tenant,cid,delivery,body_hash,now()))
        store.audit(db,tenant,'connector:'+cid,'connector.ingest',{'type':kind,'rows':len(rows),'delivery':delivery})
    return {'status':'accepted','rows':len(rows),'delivery':delivery}
