"""Publish client-safe rows only. Requires authenticated gcloud/bq CLI on job runner."""
import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from ims.core import Store
from ims import ctv

SCHEMA='date:DATE,channel:STRING,campaign:STRING,currency:STRING,model:STRING,revenue:FLOAT,orders:FLOAT,impressions:INTEGER,clicks:INTEGER,media_cost:FLOAT,roas:FLOAT,cpa:FLOAT,cpc:FLOAT,cpm:FLOAT,ctr:FLOAT,orders_per_click:FLOAT'
SAFE=set(s.split(':')[0] for s in SCHEMA.split(','))
CTV_SCHEMA='campaign:STRING,associated_orders:INTEGER,associated_net_revenue:FLOAT,unknown_network_type_orders:INTEGER,media_cost:FLOAT,associated_roas:FLOAT,associated_cpa:FLOAT,start_date:DATE,end_date:DATE,window_hours:INTEGER,currency:STRING'
def main():
    p=argparse.ArgumentParser();p.add_argument('--tenant',required=True);p.add_argument('--start',required=True);p.add_argument('--end',required=True);p.add_argument('--table',required=True);p.add_argument('--model',default='last_touch');p.add_argument('--kind',choices=['attribution','ctv'],default='attribution');p.add_argument('--window-hours',type=int,default=168);a=p.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]+:[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*',a.table):raise ValueError('Expected project:dataset.table')
    store=Store(os.environ['IMS_DB'])
    if a.kind=='ctv':
        result=ctv.report(store,a.tenant,a.start,a.end,a.window_hours)
        rows=[{**r,'start_date':a.start,'end_date':a.end,'window_hours':a.window_hours,'currency':result['currency']} for r in result['rows']]
        schema=CTV_SCHEMA
    else:
        rows=store.report(a.tenant,a.start,a.end,a.model,agency=False);schema=SCHEMA
    safe=set(s.split(':')[0] for s in schema.split(','))
    if any(set(r)!=safe for r in rows):raise ValueError('Unexpected export fields; fail closed')
    with tempfile.TemporaryDirectory() as d:
        f=Path(d)/'client-safe.ndjson'
        f.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
        # Full replacement of specified rolling window snapshot, not a partial-history merge.
        subprocess.run(['bq','load','--replace','--source_format=NEWLINE_DELIMITED_JSON',a.table,str(f),schema],check=True)
    print(json.dumps({'status':'published','rows':len(rows),'model':a.model}))
if __name__=='__main__':main()
