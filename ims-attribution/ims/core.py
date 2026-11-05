"""Money is integer minor units; all stored timestamps are canonical UTC."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

MODELS = {'first_touch', 'last_touch', 'linear', 'position_based'}

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def stamp(value):
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return d.astimezone(timezone.utc).isoformat(timespec='microseconds')

def ident(value):
    s = str(value)
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', s):
        raise ValueError('Invalid identifier')
    return s

def money(value):
    d = Decimal(str(value))
    if not d.is_finite() or d < 0 or d > Decimal('1000000000'):
        raise ValueError('Invalid amount')
    return int((d * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def canonical_channel(source, medium=''):
    s = str(source or 'direct').strip().lower()
    m = str(medium).strip().lower()
    if s in {'facebook', 'instagram', 'fb', 'ig', 'meta'}:
        return 'meta' if m in {'cpc','ppc','paid','paid_social','paidsocial'} else 'organic_social'
    if s in {'google','googleads','google_ads'}:
        return 'google_ads' if m in {'cpc','ppc','paid','paid_search'} else 'organic_search'
    if s in {'simpli.fi','simplifi','simpli_fi'}:
        return 'simplifi'
    return re.sub(r'[^a-z0-9_.-]', '_', s)[:80] or 'direct'

class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript(Path(__file__).with_name('schema.sql').read_text())

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def audit(self, db, tenant, actor, action, detail):
        db.execute('INSERT INTO audit(tenant,ts,actor,action,detail) VALUES(?,?,?,?,?)',
                   (tenant,now(),actor,action,json.dumps(detail,sort_keys=True)))

    def tenant(self, tenant, allow_closed=False):
        with self.db() as db:
            row = db.execute('SELECT * FROM tenants WHERE id=?',(tenant,)).fetchone()
            closed=db.execute('SELECT 1 FROM tenant_shutdown WHERE tenant=?',(tenant,)).fetchone()
        if not row:
            raise ValueError('Unknown tenant')
        if closed and not allow_closed:raise ValueError('Tenant has been closed')
        return dict(row)

    def create_tenant(self, tenant, currency='USD', origins=(), shop=None, shop_secret=None, tz='UTC'):
        ident(tenant)
        if currency not in {'USD','CAD','EUR','GBP','AUD','NZD'}:
            raise ValueError('v1 supports listed two-decimal currencies only')
        ZoneInfo(tz)
        bridge = secrets.token_urlsafe(32)
        admin, client = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('INSERT INTO tenants(id,currency,timezone,origins,shop,shop_secret,bridge_hash) VALUES(?,?,?,?,?,?,?)',
                       (tenant,currency,tz,json.dumps(list(origins)),shop,shop_secret,digest(bridge)))
            for token, role in [(admin,'agency'),(client,'client')]:
                db.execute('INSERT INTO keys VALUES(?,?,?,?,?,0)',(digest(token),tenant,role,'initial',now()))
            self.audit(db,tenant,'setup','tenant.create',{})
        return {'tenant':tenant,'agency_token':admin,'client_token':client,'bridge_token':bridge}

    def auth(self, token):
        with self.db() as db:
            row=db.execute('SELECT tenant,role FROM keys WHERE hash=? AND revoked=0',(digest(token),)).fetchone()
        return dict(row) if row else None

    def touch(self, tenant, data, trusted=False):
        t=self.tenant(tenant)
        # Consent denied events never create an identity or enter the attribution ledger.
        if data.get('analytics_consent') is not True:
            return {'status':'consent_denied'}
        ts=stamp(data.get('ts',now()))
        when=datetime.fromisoformat(ts)
        if when > datetime.now(timezone.utc)+timedelta(minutes=5):
            raise ValueError('Future event')
        if not trusted and when < datetime.now(timezone.utc)-timedelta(days=2):
            raise ValueError('Stale browser event')
        event, visitor=ident(data['event_id']),ident(data['visitor_id'])
        channel=canonical_channel(data.get('source'),data.get('medium',''))
        campaign=str(data.get('campaign') or '(none)')[:160]
        medium=str(data.get('medium') or '')[:80]
        with self.db() as db:
            block=db.execute('SELECT scope FROM consent_blocks WHERE tenant=? AND visitor=?',(tenant,visitor)).fetchone()
            if block and block['scope']=='analytics':return {'status':'consent_withdrawn'}
            if block:data={**data,'marketing_consent':False}
            existing=db.execute('SELECT * FROM touches WHERE tenant=? AND event_id=?',(tenant,event)).fetchone()
            values=(tenant,event,visitor,ts,channel,campaign,medium)
            if existing:
                if tuple(existing)!=values:
                    raise ValueError('Conflicting event replay')
                return {'status':'duplicate'}
            db.execute('INSERT INTO touches VALUES(?,?,?,?,?,?,?)',values)
            if data.get('marketing_consent') is True:
                signal_keys={'gclid','gbraid','wbraid','fbp','fbc'}
                incoming=data.get('signals',{})
                if not isinstance(incoming,dict):raise ValueError('Invalid signals')
                signals={k:str(v) for k,v in incoming.items()
                         if k in signal_keys and re.fullmatch(r'[A-Za-z0-9_.-]{1,512}',str(v))}
                old=db.execute('SELECT payload FROM signals WHERE tenant=? AND visitor=?',(tenant,visitor)).fetchone()
                merged=json.loads(old['payload']) if old else {}
                merged.update(signals)
                db.execute('INSERT INTO signals VALUES(?,?,?) ON CONFLICT(tenant,visitor) DO UPDATE SET payload=excluded.payload',
                           (tenant,visitor,json.dumps(merged)))
            # Browser order observations link identity only; they never create revenue.
            if data.get('order_id'):
                order=ident(data['order_id'])
                prev=db.execute('SELECT visitor FROM observations WHERE tenant=? AND order_id=?',(tenant,order)).fetchone()
                if prev and prev['visitor']!=visitor:
                    raise ValueError('Conflicting order identity')
                db.execute('INSERT INTO observations VALUES(?,?,?,?) ON CONFLICT(tenant,order_id) DO UPDATE SET marketing=excluded.marketing',
                           (tenant,order,visitor,1 if data.get('marketing_consent') is True else 0))
        return {'status':'accepted'}

    def order(self, tenant, data, db=None):
        t=self.tenant(tenant)
        if data['currency']!=t['currency']:
            raise ValueError('Currency mismatch; do not combine currencies')
        values=(tenant,ident(data['order_id']),ident(data['visitor_id']) if data.get('visitor_id') else None,
                stamp(data['ts']),data['currency'],money(data['revenue']),
                ident(data['customer_id']) if data.get('customer_id') else None,str(data.get('source','trusted_import')))
        def save(conn):
            old=conn.execute('SELECT * FROM orders WHERE tenant=? AND order_id=?',values[:2]).fetchone()
            if old and tuple(old)!=values:
                raise ValueError('Conflicting order replay; reconcile explicitly')
            conn.execute('INSERT OR IGNORE INTO orders VALUES(?,?,?,?,?,?,?,?)',values)
        if db is not None:
            save(db)
        else:
            with self.db() as conn:
                save(conn)

    def refund(self, tenant, data, db=None):
        values=(tenant,ident(data['refund_id']),ident(data['order_id']),money(data['amount']),stamp(data['ts']))
        def save(conn):
            old=conn.execute('SELECT * FROM refunds WHERE tenant=? AND refund_id=?',values[:2]).fetchone()
            if old and tuple(old)!=values:
                raise ValueError('Conflicting refund replay')
            conn.execute('INSERT OR IGNORE INTO refunds VALUES(?,?,?,?,?)',values)
        if db is not None:
            save(db)
        else:
            with self.db() as conn:
                save(conn)

    def order_snapshot(self,tenant,order_id,net,updated,source='shopify_reconciliation',db=None):
        values=(tenant,ident(order_id),stamp(updated),money(net),source)
        def save(conn):
            old=conn.execute('SELECT * FROM order_snapshots WHERE tenant=? AND order_id=?',values[:2]).fetchone()
            if old and old['updated']>values[2]:return
            if old and old['updated']==values[2] and old['net']!=values[3]:raise ValueError('Conflicting same-version snapshot')
            conn.execute('INSERT INTO order_snapshots VALUES(?,?,?,?,?) ON CONFLICT(tenant,order_id) DO UPDATE SET updated=excluded.updated,net=excluded.net,source=excluded.source',values)
        if db is not None:save(db)
        else:
            with self.db() as conn:save(conn)

    def spend(self, tenant, rows, actor='job'):
        t=self.tenant(tenant)
        with self.db() as db:
            for r in rows:
                day=datetime.strptime(r['date'],'%Y-%m-%d').date().isoformat()
                if r['currency']!=t['currency']:
                    raise ValueError('Currency mismatch')
                channel=canonical_channel(r['channel'],'paid')
                impressions,clicks=int(r['impressions']),int(r['clicks'])
                if min(impressions,clicks)<0:
                    raise ValueError('Negative count')
                db.execute('INSERT INTO spend VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant,day,channel,campaign) DO UPDATE SET currency=excluded.currency,cost=excluded.cost,impressions=excluded.impressions,clicks=excluded.clicks',
                           (tenant,day,channel,str(r['campaign'])[:160],r['currency'],money(r['cost']),impressions,clicks))
            self.audit(db,tenant,actor,'spend.upsert',{'rows':len(rows)})

    def markup(self,tenant,channel,effective,bps,actor='agency'):
        self.tenant(tenant)
        day=datetime.strptime(effective,'%Y-%m-%d').date().isoformat()
        channel='*' if channel=='*' else canonical_channel(channel,'paid')
        bps=int(bps)
        if not 0<=bps<=100000:
            raise ValueError('Markup must be 0–1000 percent')
        with self.db() as db:
            db.execute('INSERT INTO markups VALUES(?,?,?,?) ON CONFLICT(tenant,channel,effective) DO UPDATE SET bps=excluded.bps',(tenant,channel,day,bps))
            self.audit(db,tenant,actor,'markup.set',{'channel':channel,'effective':day,'basis_points':bps})

    def report(self, tenant, start, end, model='last_touch', agency=False):
        if model not in MODELS:
            raise ValueError('Unknown attribution model')
        lo=datetime.strptime(start,'%Y-%m-%d').date()
        hi=datetime.strptime(end,'%Y-%m-%d').date()
        if hi<lo or (hi-lo).days>366:
            raise ValueError('Report range must be 1–367 days')
        t=self.tenant(tenant)
        tz=ZoneInfo(t['timezone'])
        rows={}
        def bucket(day,channel,campaign):
            key=(day,channel,campaign)
            if key not in rows:
                rows[key]={'date':day,'channel':channel,'campaign':campaign,'currency':t['currency'],
                           'model':model,'revenue':0.,'orders':0.,'impressions':0,'clicks':0,'cost':0,'raw':0}
            return rows[key]
        with self.db() as db:
            lower=datetime.combine(lo,datetime.min.time(),tzinfo=tz).astimezone(timezone.utc).isoformat(timespec='microseconds')
            upper=datetime.combine(hi+timedelta(days=1),datetime.min.time(),tzinfo=tz).astimezone(timezone.utc).isoformat(timespec='microseconds')
            orders=db.execute('SELECT * FROM ledger_net WHERE tenant=? AND ts>=? AND ts<?',(tenant,lower,upper)).fetchall()
            for o in orders:
                date=datetime.fromisoformat(o['ts']).astimezone(tz).date()
                if not lo<=date<=hi:
                    continue
                # Refunds restate original order date; not a cash accounting report.
                net=o['net']/100
                visitor=o['visitor']
                if not visitor:
                    observation=db.execute('SELECT visitor FROM observations WHERE tenant=? AND order_id=?',(tenant,o['order_id'])).fetchone()
                    visitor=observation['visitor'] if observation else None
                earliest=(datetime.fromisoformat(o['ts'])-timedelta(days=t['lookback_days'])).isoformat(timespec='microseconds')
                touches=db.execute('SELECT * FROM touches WHERE tenant=? AND visitor=? AND ts>=? AND ts<=? ORDER BY ts,event_id',
                                   (tenant,visitor,earliest,o['ts'])).fetchall() if visitor else []
                # Last non-direct and first non-direct, with direct only if observed.
                non_direct=[p for p in touches if p['channel']!='direct']
                journey=non_direct or list(touches)
                if not journey:
                    credits=[('unattributed','(none)',1.)]
                else:
                    if model=='first_touch': chosen=[(journey[0],1.)]
                    elif model=='last_touch': chosen=[(journey[-1],1.)]
                    elif model=='linear': chosen=[(p,1/len(journey)) for p in journey]
                    elif len(journey)==1: chosen=[(journey[0],1.)]
                    elif len(journey)==2: chosen=[(journey[0],.5),(journey[1],.5)]
                    else: chosen=[(p,.4 if i in {0,len(journey)-1} else .2/(len(journey)-2)) for i,p in enumerate(journey)]
                    credits=[(p['channel'],p['campaign'],w) for p,w in chosen]
                for channel,campaign,w in credits:
                    b=bucket(date.isoformat(),channel,campaign)
                    b['revenue']+=net*w
                    b['orders']+=w
            for s in db.execute('SELECT * FROM spend WHERE tenant=? AND day>=? AND day<=?',(tenant,start,end)):
                rule=db.execute("SELECT bps FROM markups WHERE tenant=? AND channel IN (?, '*') AND effective<=? ORDER BY CASE WHEN channel=? THEN 0 ELSE 1 END,effective DESC LIMIT 1",(tenant,s['channel'],s['day'],s['channel'])).fetchone()
                bps=rule['bps'] if rule else 0
                billed=int((Decimal(s['cost'])*Decimal(10000+bps)/10000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                b=bucket(s['day'],s['channel'],s['campaign'])
                b['raw']+=s['cost']; b['cost']+=billed
                b['impressions']+=s['impressions']; b['clicks']+=s['clicks']
        result=[]
        for k,b in sorted(rows.items()):
            raw=b.pop('raw')/100; cost=b.pop('cost')/100
            b['media_cost']=cost
            b['revenue']=round(b['revenue'],6); b['orders']=round(b['orders'],8)
            b['roas']=b['revenue']/cost if cost else None
            b['cpa']=cost/b['orders'] if b['orders'] else None
            b['cpc']=cost/b['clicks'] if b['clicks'] else None
            b['cpm']=1000*cost/b['impressions'] if b['impressions'] else None
            b['ctr']=b['clicks']/b['impressions'] if b['impressions'] else None
            # This is orders per ad click, not Shopify session conversion rate.
            b['orders_per_click']=b['orders']/b['clicks'] if b['clicks'] else None
            if agency:
                b['vendor_cost']=raw; b['agency_gross_profit']=round(cost-raw,2)
            result.append(b)
        return result

    def customer_summary(self,tenant):
        with self.db() as db:
            rows=db.execute('SELECT customer,COUNT(*) AS orders,SUM(net) AS revenue FROM ledger_net WHERE tenant=? AND customer IS NOT NULL GROUP BY customer',(tenant,)).fetchall()
        return {'known_customers':len(rows),'repeat_customers':sum(r['orders']>1 for r in rows),
                'observed_customer_revenue':sum(r['revenue'] for r in rows)/100,
                'note':'Observed imported history only; not predicted lifetime value. Anonymous orders excluded.'}
