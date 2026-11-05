"""Local operator commands. Credentials are read from environment, never CLI flags."""
import argparse
import csv
import json
import os
import sys
from pathlib import Path
from .core import Store
from . import operations

def main():
    p=argparse.ArgumentParser(description='IMS attribution operator CLI')
    p.add_argument('--db',default=os.environ.get('IMS_DB','ims.sqlite3'))
    sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create-tenant');c.add_argument('tenant');c.add_argument('--currency',default='USD')
    c.add_argument('--timezone',default='UTC');c.add_argument('--origin',action='append',default=[]);c.add_argument('--shop')
    s=sub.add_parser('import-spend');s.add_argument('tenant');s.add_argument('csv')
    m=sub.add_parser('markup');m.add_argument('tenant');m.add_argument('--channel',default='*');m.add_argument('--effective',required=True);m.add_argument('--basis-points',required=True,type=int)
    r=sub.add_parser('export');r.add_argument('tenant');r.add_argument('--start',required=True);r.add_argument('--end',required=True);r.add_argument('--model',default='last_touch');r.add_argument('--out',required=True)
    k=sub.add_parser('revoke-key');k.add_argument('hash',help='SHA256 key fingerprint, never plaintext token')
    b=sub.add_parser('backup');b.add_argument('destination')
    n=sub.add_parser('issue-key');n.add_argument('tenant');n.add_argument('--role',choices=['agency','client'],required=True);n.add_argument('--label',required=True)
    args=p.parse_args();store=Store(args.db)
    if args.cmd=='create-tenant':
        result=store.create_tenant(args.tenant,args.currency,args.origin,args.shop,os.environ.get('SHOPIFY_WEBHOOK_SECRET'),args.timezone)
        # Redirect once to a mode-600 file; do not put this output in shared logs.
        print(json.dumps(result,indent=2))
    elif args.cmd=='import-spend':
        with open(args.csv,newline='') as f: rows=list(csv.DictReader(f))
        store.spend(args.tenant,rows);print(json.dumps({'imported':len(rows)}))
    elif args.cmd=='markup':
        store.markup(args.tenant,args.channel,args.effective,args.basis_points);print('saved')
    elif args.cmd=='revoke-key':
        with store.db() as db:db.execute('UPDATE keys SET revoked=1 WHERE hash=?',(args.hash,))
        print('revoked if present')
    elif args.cmd=='backup':print(json.dumps(operations.backup(store,args.destination)))
    elif args.cmd=='issue-key':print(json.dumps(operations.issue_key(store,args.tenant,args.role,args.label)))
    elif args.cmd=='export':
        # Export is ALWAYS client safe. No --agency switch intentionally.
        rows=store.report(args.tenant,args.start,args.end,args.model,agency=False)
        path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w') as f:
            for row in rows:f.write(json.dumps(row,allow_nan=False)+'\n')
        print(json.dumps({'rows':len(rows),'output':str(path)}))

if __name__=='__main__':main()
