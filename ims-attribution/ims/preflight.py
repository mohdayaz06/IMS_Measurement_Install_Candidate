"""Non-destructive installation validation. Never prints secret values."""
import argparse
import json
from pathlib import Path
import sqlite3

def check(directory):
    root=Path(directory);findings=[]
    for name in ['compose.json','pipeline.json','runtime.env','operator-credentials.json','destinations.json','gateways.json','Caddyfile']:
        if not (root/name).is_file():findings.append({'level':'error','item':name,'reason':'Missing generated asset'})
    if findings:return findings
    env={}
    for line in (root/'runtime.env').read_text().splitlines():
        if '=' in line and not line.startswith('#'):k,v=line.split('=',1);env[k]=v
    for k,v in env.items():
        if any(s in v for s in ['REPLACE_','replace_','example.com']):findings.append({'level':'action','item':k,'reason':'Replace installation placeholder'})
    db=root/'data/ims.sqlite3'
    with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':findings.append({'level':'error','item':'database','reason':'Integrity check failed'})
        for tenant,shop,secret in conn.execute('SELECT id,shop,shop_secret FROM tenants'):
            if shop and not secret:findings.append({'level':'action','item':tenant+':shopify','reason':'Webhook app secret is not configured'})
    config=json.loads((root/'pipeline.json').read_text())
    for job in config['jobs']:
        required=[]
        if job['kind']=='shopify_reconcile':
            o=job['options'];required=[o['token_env'],o['version_env']]
        if job['kind']=='google_spend':
            required=['GOOGLE_ADS_API_VERSION','GOOGLE_ADS_DEVELOPER_TOKEN','GOOGLE_ADS_CUSTOMER_ID']
        if job['kind']=='meta_spend':required=['META_API_VERSION','META_AD_ACCOUNT_ID','META_ACCESS_TOKEN']
        mapped=job.get('environment',{})
        for name in required:
            actual=mapped.get(name,name)
            if not env.get(actual):findings.append({'level':'action','item':job['id']+':'+actual,'reason':'Required credential/configuration absent'})
    findings.append({'level':'info','item':'live_validation','reason':'Run installed acceptance checklist for GTM, merchant checkout and vendor receipt; local checks do not establish platform acceptance.'})
    return findings

def main():
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args();r=check(a.directory);print(json.dumps(r,indent=2))
    if any(x['level']=='error' for x in r):raise SystemExit(1)
if __name__=='__main__':main()
