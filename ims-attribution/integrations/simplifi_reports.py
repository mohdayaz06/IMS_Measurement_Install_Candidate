"""Automated import of account-authorized Simpli.fi scheduled CSV exports.
Feed can be locally delivered (SFTP/email ingestion operated by merchant) or HTTPS
download with optional bearer auth. Never invents a vendor reporting API endpoint.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request
from urllib.parse import urlsplit
from ims.core import now
from ims import ctv
from .universal_csv import payload_from_csv
from .http_client import NoRedirect

def read_feed(config):
    if config.get('path'):
        path=Path(config['path'])
        if not path.is_absolute():raise ValueError('Use approved absolute feed path')
        return path.read_bytes()
    url=config['url'];u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.hostname!=config['allowed_hostname']:
        raise ValueError('Use approved HTTPS feed host')
    headers={}
    if config.get('token_env'):headers['Authorization']='Bearer '+os.environ[config['token_env']]
    with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url,headers=headers),timeout=30) as response:
        raw=response.read(20*1024*1024+1)
    if len(raw)>20*1024*1024:raise ValueError('Feed exceeds 20 MiB; split export')
    return raw

def run(store,tenant,config):
    raw=read_feed(config)
    if config.get('max_age_hours') and config.get('path'):
        import time
        if time.time()-Path(config['path']).stat().st_mtime>float(config['max_age_hours'])*3600:raise ValueError('Stale delivered feed')
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'feed.csv';path.write_bytes(raw)
        if config['type']=='spend':
            rows=payload_from_csv(path,config['mapping'])['rows']
            for r in rows:
                r['channel']=config.get('channel','simplifi')
                if config.get('campaign_prefix'):r['campaign']=config['campaign_prefix']+r['campaign']
            if not rows:raise ValueError('Empty spend report; do not overwrite/assume zero')
            store.spend(tenant,rows,'simplifi-scheduled-report')
        elif config['type'] in {'ctv_impressions','order_networks'}:
            fields=config['mapping']['fields'];rows=[]
            with path.open(newline='',encoding='utf-8-sig') as f:
                for source in csv.DictReader(f):
                    r={k:source[v] for k,v in fields.items()}
                    # Rights declaration is installation config, not blindly inferred from logs.
                    r['measurement_permitted']=config.get('measurement_permitted') is True
                    r['network_type']=r.get('network_type','unknown')
                    if config['type']=='ctv_impressions':
                        r['provider']='simplifi'
                        if config.get('campaign_prefix'):r['campaign']=config['campaign_prefix']+r['campaign']
                    rows.append(r)
            (ctv.impressions if config['type']=='ctv_impressions' else ctv.link_orders)(store,tenant,rows)
        else:raise ValueError('Unknown Simpli.fi report type')
    return {'rows':len(rows),'feed_sha256':hashlib.sha256(raw).hexdigest()}
