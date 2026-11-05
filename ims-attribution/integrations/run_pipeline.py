"""Supervised single-host jobs. Configuration contains env-variable names, not secrets.
On failure, later jobs for that tenant are skipped to avoid publishing partial results.
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from ims.core import Store,now
from . import spend_sync

def execute(store,tenant,job):
    opts=job.get('options',{});kind=job['kind'];t=store.tenant(tenant)
    end=(datetime.now(ZoneInfo(t['timezone'])).date()-timedelta(days=int(opts.get('end_days_ago',1))))
    days=int(opts.get('days',7))
    if not 1<=days<=367:raise ValueError('Job window out of range')
    start=end-timedelta(days=days-1)
    if kind=='database_backup':
        from ims.operations import backup
        directory=Path(opts.get('directory','/data/backups'));directory.mkdir(parents=True,exist_ok=True)
        filename='ims-'+datetime.fromisoformat(now()).strftime('%Y%m%dT%H%M%S%f')+'.sqlite3'
        result=backup(store,str((directory/filename).resolve()))
        keep=int(opts.get('keep',7))
        if keep<1:raise ValueError('Keep at least one backup')
        for stale in sorted(directory.glob('ims-*.sqlite3'),key=lambda x:x.stat().st_mtime,reverse=True)[keep:]:stale.unlink()
        return result
    if kind=='simplifi_feed':
        from .simplifi_reports import run as feed_run
        return feed_run(store,tenant,opts['feed'])
    if kind=='native_conversions':
        from .destinations import run as native_run
        with open(os.environ['IMS_DESTINATIONS_FILE']) as f:configs=json.load(f)
        return native_run(store,{tenant:configs.get(tenant,[])})
    if kind=='woocommerce_reconcile':
        from .commerce_sync import woo_sync
        return woo_sync(store,tenant,opts['base_url'],start.isoformat()+'T00:00:00Z',os.environ[opts['key_env']],os.environ[opts['secret_env']])
    if kind=='bigcommerce_reconcile':
        from .commerce_sync import bigcommerce_sync
        return bigcommerce_sync(store,tenant,opts['store_hash'],start.isoformat()+'T00:00:00Z',os.environ[opts['token_env']],opts['paid_status_ids'])
    if kind=='shopify_reconcile':
        from .shopify_sync import sync
        token=os.environ[opts.get('token_env','SHOPIFY_ADMIN_ACCESS_TOKEN')]
        version=os.environ.get(opts.get('version_env','SHOPIFY_API_VERSION'),'')
        return sync(store,tenant,start.isoformat()+'T00:00:00Z',version,token)
    if kind in {'google_spend','meta_spend'}:
        # Map a per-account secret ENV NAME into the vendor job's expected ENV NAME.
        # Values stay in process environment and never appear in audit output.
        saved={}
        try:
            for target,source_name in job.get('environment',{}).items():
                if not target.startswith(('GOOGLE_ADS_','META_')):raise ValueError('Unexpected vendor environment key')
                saved[target]=os.environ.get(target)
                os.environ[target]=os.environ[source_name]
            rows=list((spend_sync.google if kind=='google_spend' else spend_sync.meta)(start.isoformat(),end.isoformat()))
            if opts.get('campaign_prefix'):
                for r in rows:r['campaign']=opts['campaign_prefix']+str(r['campaign'])
            store.spend(tenant,rows,'scheduled-job')
            return {'rows':len(rows)}
        finally:
            for key,value in saved.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
    if kind=='bigquery_export':
        args=[sys.executable,'-m','integrations.export_bigquery','--tenant',tenant,'--start',start.isoformat(),
              '--end',end.isoformat(),'--table',opts['table'],'--kind',opts.get('report_kind','attribution'),
              '--model',opts.get('model','last_touch'),'--window-hours',str(opts.get('window_hours',168))]
        env={**os.environ,'IMS_DB':store.path}
        p=subprocess.run(args,capture_output=True,timeout=240,env=env)
        if p.returncode:raise RuntimeError('Export failed; no report payload logged')
        return {'published':True}
    if kind=='conversion_outbox':
        from .deliver_conversions import deliver
        with open(os.environ[opts.get('config_env','IMS_GATEWAYS_FILE')]) as f:config=json.load(f)
        # deliver scopes through config; filter to this tenant to avoid duplicate sends across jobs.
        deliver(store,{tenant:config[tenant]})
        return {'attempted':True}
    if kind=='experiment_ip_sync':
        from ims import ctv
        return {'orders':ctv.sync_outcomes(store,tenant,opts['experiment'])['orders']}
    raise ValueError('Unknown job kind')

def run(store,config):
    failed=set();summaries=[]
    for job in config['jobs']:
        tenant=job['tenant'];store.tenant(tenant)
        if tenant in failed and job['kind']!='database_backup':
            summaries.append({'tenant':tenant,'job':job['id'],'state':'skipped_due_to_prior_failure'});continue
        interval=int(job.get('interval_seconds',60 if job['kind'] in {'native_conversions','conversion_outbox'} else 3600))
        with store.db() as db:
            previous=db.execute("SELECT finished FROM job_runs WHERE tenant=? AND job=? AND state='succeeded' ORDER BY id DESC LIMIT 1",(tenant,job['id'])).fetchone()
        if previous and previous['finished'] and (datetime.fromisoformat(now())-datetime.fromisoformat(previous['finished'])).total_seconds()<interval:
            summaries.append({'tenant':tenant,'job':job['id'],'state':'not_due'});continue
        with store.db() as db:
            cursor=db.execute('INSERT INTO job_runs(tenant,job,started,state) VALUES(?,?,?,?)',(tenant,job['id'],now(),'running'))
            run_id=cursor.lastrowid
        try:
            detail=execute(store,tenant,job);state='succeeded'
        except Exception as error:
            # Exception messages/URLs can contain vendor request credentials. Only class is retained.
            detail={'error_type':type(error).__name__};state='failed';failed.add(tenant)
        with store.db() as db:
            db.execute('UPDATE job_runs SET finished=?,state=?,detail=? WHERE id=?',(now(),state,json.dumps(detail),run_id))
        summaries.append({'tenant':tenant,'job':job['id'],'state':state,**detail})
    return summaries

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--lock',default='/tmp/ims-pipeline.lock');a=p.parse_args()
    with open(a.config) as f:config=json.load(f)
    with open(a.lock,'a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Another runner is active')
        results=run(Store(os.environ['IMS_DB']),config)
        print(json.dumps(results))
        if any(r['state']=='failed' for r in results):raise SystemExit(1)
if __name__=='__main__':main()
