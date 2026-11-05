"""Native Google/Meta + signed generic conversion receivers. No fake platform receipt.
Only operator-approved per-tenant destination configurations are accepted.
"""
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
from ims.core import now
from .http_client import call,oauth_refresh,VendorError

class MissingIdentifier(Exception):pass

def purchase(store,tenant,order_id):
    with store.db() as db:
        o=db.execute('SELECT o.*,x.visitor AS observed_visitor,x.marketing FROM orders o JOIN observations x ON x.tenant=o.tenant AND x.order_id=o.order_id WHERE o.tenant=? AND o.order_id=?',(tenant,order_id)).fetchone()
        if not o:return None
        blocked=db.execute('SELECT 1 FROM consent_blocks WHERE tenant=? AND visitor=?',(tenant,o['observed_visitor'])).fetchone()
        if not o['marketing'] or blocked:return None
        signals=db.execute('SELECT payload FROM signals WHERE tenant=? AND visitor=?',(tenant,o['observed_visitor'])).fetchone()
    event_id=hashlib.sha256((tenant+':purchase:'+order_id).encode()).hexdigest()
    origins=json.loads(store.tenant(tenant)['origins'])
    return {'order_id':order_id,'value':o['gross']/100,'currency':o['currency'],'ts':o['ts'],
        'visitor':o['observed_visitor'],'event_id':event_id,'signals':json.loads(signals['payload']) if signals else {},
        'source_url':origins[0]+'/' if origins else None}

def deliver_google(p,config):
    ids=p['signals'];selected=next((key for key in ['gclid','gbraid','wbraid'] if ids.get(key)),None)
    if not selected:raise MissingIdentifier('No Google ad click identifier')
    customer=str(config['customer_id']).replace('-','');action=str(config['conversion_action_id'])
    version=config['api_version']
    if not customer.isdigit() or not action.isdigit() or not re.fullmatch(r'v\d+',version):raise ValueError('Invalid Google destination IDs/version')
    prefix=config.get('credential_prefix','GOOGLE_ADS')
    headers={'Authorization':'Bearer '+oauth_refresh(prefix),'developer-token':os.environ[config.get('developer_token_env','GOOGLE_ADS_DEVELOPER_TOKEN')]}
    if config.get('login_customer_id'):headers['login-customer-id']=str(config['login_customer_id']).replace('-','')
    date=datetime.fromisoformat(p['ts']).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S+00:00')
    conversion={selected:ids[selected],'conversionAction':'customers/'+customer+'/conversionActions/'+action,
        'conversionDateTime':date,'conversionValue':p['value'],'currencyCode':p['currency'],'orderId':p['order_id'],
        'consent':{'adUserData':'GRANTED','adPersonalization':'GRANTED'}}
    result=call('https://googleads.googleapis.com/'+version+'/customers/'+customer+':uploadClickConversions',headers,
                {'conversions':[conversion],'partialFailure':True,'validateOnly':bool(config.get('validate_only',False))})
    if result.get('partialFailureError'):raise VendorError(422)
    if not config.get('validate_only') and not result.get('results'):raise VendorError(422)
    return 'validated_only' if config.get('validate_only') else 'provider_accepted'

def deliver_meta(p,config):
    user={k:p['signals'][k] for k in ['fbc','fbp'] if p['signals'].get(k)}
    if not user:raise MissingIdentifier('No consented Meta matching identifier')
    if not p['source_url']:raise ValueError('Merchant origin required')
    pixel=str(config['pixel_id']);version=config['api_version']
    if not pixel.isdigit() or not re.fullmatch(r'v\d+\.\d+',version):raise ValueError('Invalid Meta IDs/version')
    event={'event_name':'Purchase','event_time':int(datetime.fromisoformat(p['ts']).timestamp()),'event_id':p['event_id'],
        'action_source':'website','event_source_url':p['source_url'],'user_data':user,
        'custom_data':{'value':p['value'],'currency':p['currency'],'order_id':p['order_id']}}
    body={'data':[event]}
    if config.get('test_event_code'):body['test_event_code']=config['test_event_code']
    result=call('https://graph.facebook.com/'+version+'/'+pixel+'/events',
        {'Authorization':'Bearer '+os.environ[config.get('token_env','META_ACCESS_TOKEN')]},body)
    if result.get('events_received')!=1 or result.get('error'):raise VendorError(422)
    return 'test_received' if config.get('test_event_code') else 'provider_accepted'

def deliver_generic(p,config):
    # For a vendor-supported receiver or IMS-controlled adapter; not arbitrary vendor pixels.
    endpoint=config['endpoint'];u=urlsplit(endpoint)
    if u.scheme!='https' or u.username or u.password or u.hostname!=config['allowed_hostname']:
        raise ValueError('Endpoint must match configured approved HTTPS host')
    secret=os.environ[config['secret_env']]
    if len(secret)<32:raise ValueError('Receiver secret too short')
    body={k:p[k] for k in ['order_id','value','currency','ts','event_id']}
    raw=json.dumps(body,separators=(',',':')).encode();timestamp=str(int(time.time()))
    sig=hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    result=call(endpoint,{'X-IMS-Timestamp':timestamp,'X-IMS-Signature':sig},body)
    if result.get('accepted') is not True:raise VendorError(422)
    return 'receiver_accepted'

def run(store,config):
    counts={}
    for tenant,destinations in config.items():
        store.tenant(tenant)
        for destination in destinations:
            if not destination.get('enabled',False):continue
            name=destination['id']
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):raise ValueError('Invalid destination ID')
            with store.db() as db:
                orders=db.execute('SELECT o.order_id FROM orders o JOIN observations x ON x.tenant=o.tenant AND x.order_id=o.order_id WHERE o.tenant=? AND x.marketing=1',(tenant,)).fetchall()
                for order in orders:
                    event=hashlib.sha256((tenant+':purchase:'+order['order_id']).encode()).hexdigest()
                    db.execute('INSERT OR IGNORE INTO destination_deliveries(tenant,order_id,destination,event_id,state,next_attempt) VALUES(?,?,?,?,?,?)',(tenant,order['order_id'],name,event,'pending',now()))
                pending=db.execute("SELECT * FROM destination_deliveries WHERE tenant=? AND destination=? AND state IN ('pending','awaiting_identifier') AND next_attempt<=? ORDER BY next_attempt LIMIT 100",(tenant,name,now())).fetchall()
            for row in pending:
                p=purchase(store,tenant,row['order_id']);status=0;detail={}
                if p is None:state='consent_blocked'
                elif (datetime.now(timezone.utc)-datetime.fromisoformat(p['ts'])).total_seconds()>int(destination.get('max_age_hours',72))*3600:
                    state='expired';detail={'reason':'Configured destination event age exceeded'}
                else:
                    try:
                        adapter={'google_ads':deliver_google,'meta':deliver_meta,'signed_webhook':deliver_generic}[destination['type']]
                        state=adapter(p,destination);status=200
                    except MissingIdentifier:state='awaiting_identifier'
                    except VendorError as error:
                        status=error.status
                        state='pending' if error.retryable and row['attempts']<7 else 'dead_letter'
                    except Exception:
                        state='configuration_error';detail={'reason':'Check destination configuration/credentials; payload not logged'}
                delay=3600 if state=='awaiting_identifier' else min(3600,30*2**min(row['attempts']+1,7))
                nxt=(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(timespec='microseconds')
                with store.db() as db:
                    db.execute('UPDATE destination_deliveries SET state=?,attempts=attempts+1,next_attempt=?,last_status=?,detail=? WHERE tenant=? AND order_id=? AND destination=?',(state,nxt,status,json.dumps(detail),tenant,row['order_id'],name))
                counts[state]=counts.get(state,0)+1
    return counts

if __name__=='__main__':
    with open(os.environ['IMS_DESTINATIONS_FILE']) as f:config=json.load(f)
    print(json.dumps(run(__import__('ims.core',fromlist=['Store']).Store(os.environ['IMS_DB']),config)))
