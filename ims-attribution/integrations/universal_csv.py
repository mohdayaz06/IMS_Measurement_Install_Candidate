"""Map any approved vendor CSV into IMS canonical spend and send signed ingestion.
Mapping JSON is operator-owned configuration, not a remote executable expression.
"""
import argparse
import csv
from decimal import Decimal
import hashlib
import hmac
import json
import os
import time
import urllib.request
import uuid
from urllib.parse import urlsplit

def normalize(source,mapping):
    fields=mapping['fields'];constant=mapping.get('constants',{})
    def value(name,default=None):
        return source[fields[name]] if name in fields else constant.get(name,default)
    return {'date':value('date'),'campaign':str(value('campaign')),'currency':value('currency'),
            'cost':str(Decimal(str(value('cost')))*Decimal(str(mapping.get('cost_multiplier','1')))),
            'impressions':int(value('impressions',0)),'clicks':int(value('clicks',0))}

def payload_from_csv(path,mapping):
    # Aggregate fragmented rows before upsert; never overwrite ad-set fragments of a campaign.
    grouped={}
    with open(path,newline='',encoding='utf-8-sig') as f:
        for source in csv.DictReader(f):
            r=normalize(source,mapping);k=(r['date'],r['campaign'],r['currency'])
            if k not in grouped:grouped[k]={**r,'cost':Decimal(r['cost'])}
            else:
                grouped[k]['cost']+=Decimal(r['cost']);grouped[k]['impressions']+=r['impressions'];grouped[k]['clicks']+=r['clicks']
    return {'type':'spend','rows':[{**r,'cost':str(r['cost'])} for r in grouped.values()]}

def send(endpoint,payload,secret):
    u=urlsplit(endpoint)
    if u.scheme!='https' or not u.path.startswith('/ingest/') or u.username or u.password:
        raise ValueError('Use fixed HTTPS ingestion endpoint')
    if len(secret)<32:raise ValueError('Signing secret too short')
    raw=json.dumps(payload,separators=(',',':')).encode()
    if len(raw)>1024*1024:raise ValueError('Batch exceeds 1 MiB')
    timestamp=str(int(time.time()));delivery=str(uuid.uuid4())
    signature=hmac.new(secret.encode(),timestamp.encode()+b'.'+delivery.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    req=urllib.request.Request(endpoint,data=raw,headers={'Content-Type':'application/json','X-IMS-Timestamp':timestamp,
                 'X-IMS-Delivery':delivery,'X-IMS-Signature':signature})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=45) as r:return json.load(r)

def main():
    p=argparse.ArgumentParser();p.add_argument('--csv',required=True);p.add_argument('--mapping',required=True);p.add_argument('--endpoint',required=True);a=p.parse_args()
    with open(a.mapping) as f:mapping=json.load(f)
    payload=payload_from_csv(a.csv,mapping)
    for offset in range(0,len(payload['rows']),500):
        result=send(a.endpoint,{'type':'spend','rows':payload['rows'][offset:offset+500]},os.environ['IMS_INGEST_SECRET'])
        print(json.dumps({'status':result['status'],'rows':result.get('rows',0)}))
if __name__=='__main__':main()
