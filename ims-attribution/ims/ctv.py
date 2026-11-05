"""Exact-IP CTV association, kept separate from click attribution and causal lift."""
import hashlib
import hmac
import ipaddress
import os
from datetime import datetime,timedelta
from .core import ident,now,stamp
from . import experiments

def network_key(tenant,address):
    # Raw IP never persists. HMAC is pseudonymization, not anonymization.
    root=os.environ.get('IMS_IP_HMAC_KEY','')
    if len(root)<32:
        raise ValueError('Configure IMS_IP_HMAC_KEY with >=32 random characters')
    ip=ipaddress.ip_address(address)
    if getattr(ip,'ipv4_mapped',None):ip=ip.ipv4_mapped
    if not ip.is_global:
        raise ValueError('CTV requires public viewer IP, not private/server/proxy address')
    key=hmac.new(root.encode(),tenant.encode(),hashlib.sha256).digest()
    return hmac.new(key,ip.compressed.encode(),hashlib.sha256).hexdigest()

def permitted(data):
    if data.get('measurement_permitted') is not True:
        raise ValueError('Authorized measurement/consent signal required')
    if data.get('network_type','unknown') not in {'residential','unknown'}:
        raise ValueError('Reject known proxy, VPN, datacenter, shared or SSAI-server IP')

def impressions(store,tenant,rows):
    store.tenant(tenant)
    with store.db() as db:
        for r in rows:
            permitted(r)
            ts=stamp(r['ts'])
            if ts>now():raise ValueError('Future impression')
            values=(tenant,ident(r['impression_id']),network_key(tenant,r['ip_address']),ts,
                    str(r['campaign'])[:160],str(r['provider'])[:80],r.get('network_type','unknown'))
            old=db.execute('SELECT * FROM ctv_impressions WHERE tenant=? AND impression_id=?',values[:2]).fetchone()
            if old and tuple(old)!=values:raise ValueError('Conflicting impression replay')
            db.execute('INSERT OR IGNORE INTO ctv_impressions VALUES(?,?,?,?,?,?,?)',values)
        store.audit(db,tenant,'agency','ctv.impressions',{'rows':len(rows)})

def link_orders(store,tenant,rows):
    with store.db() as db:
        for r in rows:
            permitted(r)
            values=(tenant,ident(r['order_id']),network_key(tenant,r['ip_address']))
            if not db.execute('SELECT 1 FROM orders WHERE tenant=? AND order_id=?',values[:2]).fetchone():
                raise ValueError('Verified order must exist before IP association')
            old=db.execute('SELECT * FROM ctv_order_networks WHERE tenant=? AND order_id=?',values[:2]).fetchone()
            if old and tuple(old)!=values:raise ValueError('Conflicting order IP association')
            db.execute('INSERT OR IGNORE INTO ctv_order_networks VALUES(?,?,?)',values)
        store.audit(db,tenant,'agency','ctv.order_networks',{'rows':len(rows)})

def report(store,tenant,start,end,window_hours=168):
    window=int(window_hours)
    if not 1<=window<=720:raise ValueError('Window must be 1–720 hours')
    lo=datetime.strptime(start,'%Y-%m-%d').date();hi=datetime.strptime(end,'%Y-%m-%d').date()
    if hi<lo or (hi-lo).days>366:raise ValueError('Invalid report range')
    from zoneinfo import ZoneInfo
    t=store.tenant(tenant);tz=ZoneInfo(t['timezone'])
    counts={};total=0;ip_eligible=0;matched=0
    with store.db() as db:
        orders=db.execute('SELECT o.*,n.network_key FROM ledger_net o LEFT JOIN ctv_order_networks n ON n.tenant=o.tenant AND n.order_id=o.order_id WHERE o.tenant=?',(tenant,)).fetchall()
        for o in orders:
            date=datetime.fromisoformat(o['ts']).astimezone(tz).date()
            if not lo<=date<=hi:continue
            total+=1
            if not o['network_key']:continue
            ip_eligible+=1
            first=(datetime.fromisoformat(o['ts'])-timedelta(hours=window)).isoformat(timespec='microseconds')
            impression=db.execute('SELECT * FROM ctv_impressions WHERE tenant=? AND network_key=? AND ts>=? AND ts<=? ORDER BY ts DESC,impression_id DESC LIMIT 1',(tenant,o['network_key'],first,o['ts'])).fetchone()
            if not impression:continue
            matched+=1
            k=impression['campaign']
            c=counts.setdefault(k,{'campaign':k,'associated_orders':0,'associated_net_revenue':0.,'unknown_network_type_orders':0})
            c['associated_orders']+=1;c['associated_net_revenue']+=o['net']/100
            c['unknown_network_type_orders']+=impression['network_type']=='unknown'
    # Pricing is reused from safe report builder; vendor cost never enters this output.
    cost={}
    for r in store.report(tenant,start,end):
        if r['channel']=='ctv':cost[r['campaign']]=cost.get(r['campaign'],0)+r['media_cost']
    for campaign in cost:counts.setdefault(campaign,{'campaign':campaign,'associated_orders':0,'associated_net_revenue':0.,'unknown_network_type_orders':0})
    for c in counts.values():
        c['media_cost']=cost.get(c['campaign'],0)
        c['associated_roas']=c['associated_net_revenue']/c['media_cost'] if c['media_cost'] else None
        c['associated_cpa']=c['media_cost']/c['associated_orders'] if c['associated_orders'] else None
    return {'measurement':'CTV exact-IP last eligible impression household association',
            'currency':t['currency'],'window_hours':window,'total_verified_orders':total,
            'ip_eligible_orders':ip_eligible,'associated_orders':matched,
            'association_rate_among_ip_eligible':matched/ip_eligible if ip_eligible else None,
            'rows':[counts[k] for k in sorted(counts)],
            'warning':'View-through household/network association is not causal lift. Do not add these sales to click-attributed sales; the same order can appear in both views.'}

def enroll_ip(store,tenant,experiment,data):
    permitted(data)
    with store.db() as db:
        e=db.execute('SELECT unit_type FROM experiments WHERE tenant=? AND id=?',(tenant,experiment)).fetchone()
    if not e or e['unit_type']!='household_ip':raise ValueError('Requires household_ip experiment')
    return experiments.enroll(store,tenant,experiment,network_key(tenant,data['ip_address']))

def sync_outcomes(store,tenant,experiment):
    # Enrollment must precede test start; sync purchases for BOTH arms, not exposed only.
    with store.db() as db:
        e=db.execute('SELECT * FROM experiments WHERE tenant=? AND id=?',(tenant,experiment)).fetchone()
        if not e or e['unit_type']!='household_ip':raise ValueError('Requires household_ip experiment')
        rows=db.execute('SELECT o.*,n.network_key FROM ledger_net o JOIN ctv_order_networks n ON n.tenant=o.tenant AND n.order_id=o.order_id JOIN units u ON u.tenant=o.tenant AND u.experiment=? AND u.unit=n.network_key WHERE o.tenant=? AND o.ts>=? AND o.ts<?',(experiment,tenant,e['start'],e['end'])).fetchall()
    for o in rows:
        # This trusted reconciliation path reads current merchant net directly. It can
        # update prior gross outcomes after a refund without accepting arbitrary user edits.
        with store.db() as db:
            old=db.execute('SELECT unit,revenue FROM outcomes WHERE tenant=? AND experiment=? AND outcome=?',(tenant,experiment,o['order_id'])).fetchone()
            if old and old['unit']!=o['network_key']:raise ValueError('Outcome network changed; analyst review required')
            db.execute('INSERT INTO outcomes VALUES(?,?,?,?,?,?) ON CONFLICT(tenant,experiment,outcome) DO UPDATE SET revenue=excluded.revenue,ts=excluded.ts',
                (tenant,experiment,o['order_id'],o['network_key'],o['ts'],o['net']))
            if old and old['revenue']!=o['net']:
                db.execute('DELETE FROM experiment_publications WHERE tenant=? AND experiment=?',(tenant,experiment))
                store.audit(db,tenant,'merchant-reconciliation','experiment.outcome_restate',{'experiment':experiment})
    return {'status':'synced','orders':len(rows),'note':'Both arms included; revised net outcomes unpublish prior results for analyst review.'}
