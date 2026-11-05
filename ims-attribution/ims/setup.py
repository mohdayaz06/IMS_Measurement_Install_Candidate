"""Generate a per-installation deployment bundle from one operator-owned JSON file.
No infrastructure or accounts are changed. Never run on an existing production output.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from .core import Store,ident

ROOT=Path(__file__).resolve().parent.parent

def origin(value):
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.path not in {'','/'} or u.query or u.fragment:
        raise ValueError('Use exact HTTPS origins')
    return 'https://'+u.netloc

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value);path.chmod(0o600)

def configure(config,out):
    if not config.get('tenants'):raise ValueError('At least one tenant is required')
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Output must be empty; never overwrite production data/secrets')
    out.mkdir(parents=True,exist_ok=True);out.chmod(0o700)
    base=origin(config['api_origin']);domain=urlsplit(base).hostname
    data=out/'data';data.mkdir(exist_ok=True);data.chmod(0o700)
    db=data/'ims.sqlite3';store=Store(db)
    env={'IMS_DB':'/data/ims.sqlite3','IMS_IP_HMAC_KEY':secrets.token_urlsafe(48),
         'IMS_CUSTOMER_HMAC_KEY':secrets.token_urlsafe(48),'IMS_DESTINATIONS_FILE':'/config/destinations.json',
         'IMS_GATEWAYS_FILE':'/config/gateways.json'}
    for key in config.get('copy_environment',[]):
        if key in os.environ:env[key]=os.environ[key]
    credentials=[];jobs=[];destinations={};gateways={}
    for client in config['tenants']:
        tenant=ident(client['id']);origins=[origin(x) for x in client['store_origins']]
        shop=client.get('shopify',{});secret=os.environ.get(shop.get('webhook_secret_env',''))
        keys=store.create_tenant(tenant,client.get('currency','USD'),origins,shop.get('shop'),secret,client.get('timezone','UTC'))
        credentials.append(keys)
        tag_origin=origin(client['sgtm_origin']);gateway=secrets.token_urlsafe(48)
        gateways[tenant]={'endpoint':tag_origin+'/ims/verified','key':gateway}
        collect=tag_origin+'/ims/events/'+tenant
        asset=out/'installers'/tenant;asset.mkdir(parents=True,exist_ok=True)
        sdk=(ROOT/'dist/shopify-custom-pixel.js').read_text()
        sdk=sdk.replace("'https://tracking.example.com'",json.dumps(base)).replace("'replace-client-id'",json.dumps(tenant)).replace("'https://tags.example.com/ims/events/replace-client-id'",json.dumps(collect))
        simpli=client.get('simplifi',{}).get('browser_tag')
        if simpli:
            sdk=sdk.replace('collectUrl:IMS_COLLECT_URL','collectUrl:IMS_COLLECT_URL,simpli:'+json.dumps(simpli,separators=(',',':')))
        write(asset/'shopify-pixel.js',sdk)
        write(asset/'sgtm-settings.json',json.dumps({'client_template':'dist/ims-http-client.tpl',
            'collectPath':'/ims/events/'+tenant,'verifiedPath':'/ims/verified','allowedOrigins':','.join(origins),
            'gatewayKey':gateway,'ledger_tag_template':'dist/ims-ledger-forwarder.tpl',
            'endpoint':base+'/bridge/'+tenant,'bridgeKey':keys['bridge_token'],
            'ledger_trigger':'Custom event ims_touch'},indent=2))
        if shop:
            jobs.append({'tenant':tenant,'id':'shopify-reconciliation','kind':'shopify_reconcile','options':{
                'days':14,'end_days_ago':0,'token_env':shop.get('token_env','SHOPIFY_ADMIN_ACCESS_TOKEN'),
                'version_env':shop.get('version_env','SHOPIFY_API_VERSION')}})
        for vendor in ['google','meta']:
            settings=client.get(vendor,{})
            for source in settings.get('environment',{}).values():
                if source in os.environ:env[source]=os.environ[source]
            if settings.get('spend'):
                jobs.append({'tenant':tenant,'id':vendor+'-spend','kind':vendor+'_spend',
                    'options':{'days':7},'environment':settings.get('environment',{})})
        for i,feed in enumerate(client.get('simplifi',{}).get('feeds',[])):
            jobs.append({'tenant':tenant,'id':'simplifi-feed-'+str(i),'kind':'simplifi_feed','options':{'feed':feed}})
        destinations[tenant]=client.get('native_destinations',[])
        if destinations[tenant]:
            jobs.append({'tenant':tenant,'id':'native-conversions','kind':'native_conversions','options':{}})
        if client.get('sgtm_purchase_forwarding',False):
            if any(d.get('enabled') for d in destinations[tenant]):raise ValueError('Choose native or sGTM delivery to avoid duplicate destination sends')
            jobs.append({'tenant':tenant,'id':'sgtm-purchases','kind':'conversion_outbox','options':{}})
        if shop:
            for source in [shop.get('token_env','SHOPIFY_ADMIN_ACCESS_TOKEN'),shop.get('version_env','SHOPIFY_API_VERSION')]:
                if source in os.environ:env[source]=os.environ[source]
        write(asset/'web-install.html','<script src="'+base+'/pixel.js"></script>\n<script>\nwindow.imsTracker=IMSAttribution.create('+json.dumps({'baseUrl':base,'tenant':tenant,'collectUrl':collect,'simpli':simpli})+');\n// CMP must call imsTracker.consent(analyticsAllowed,marketingAllowed), then pageView(location.href,document.referrer).\n</script>\n')
    jobs.append({'tenant':config['tenants'][0]['id'],'id':'daily-backup','kind':'database_backup',
                 'interval_seconds':86400,'options':{'directory':'/data/backups','keep':7}})
    write(out/'operator-credentials.json',json.dumps(credentials,indent=2))
    write(out/'pipeline.json',json.dumps({'jobs':jobs},indent=2))
    write(out/'destinations.json',json.dumps(destinations,indent=2));write(out/'gateways.json',json.dumps(gateways,indent=2))
    write(out/'runtime.env','\n'.join(k+'='+str(v) for k,v in env.items())+'\n')
    uid=os.getuid() if os.getuid()!=0 else 10001;gid=os.getgid() if os.getuid()!=0 else 10001
    compose={
      'services':{
        'api':{'build':str(ROOT),'user':str(uid)+':'+str(gid),'restart':'unless-stopped',
               'env_file':['./runtime.env'],'ports':['127.0.0.1:8080:8080'],
               'volumes':['./data:/data','./gateways.json:/config/gateways.json:ro','./destinations.json:/config/destinations.json:ro']},
        'jobs':{'build':str(ROOT),'user':str(uid)+':'+str(gid),'restart':'unless-stopped','env_file':['./runtime.env'],
                'volumes':['./data:/data','./pipeline.json:/config/pipeline.json:ro','./gateways.json:/config/gateways.json:ro','./destinations.json:/config/destinations.json:ro'],
                'command':['python','-m','integrations.scheduler','--config','/config/pipeline.json']}
      }}
    for mount in config.get('feed_mounts',[]):
        host=str(Path(mount['host']).resolve());target=mount['container']
        if not target.startswith('/feeds'):raise ValueError('Feed mount must be under /feeds')
        compose['services']['jobs']['volumes'].append(host+':'+target+':ro')
    write(out/'compose.json',json.dumps(compose,indent=2))
    caddy=(ROOT/'deploy/Caddyfile').read_text().replace('tracking.example.com',domain)
    write(out/'Caddyfile',caddy)
    connector=out/'looker-connector';connector.mkdir(exist_ok=True)
    write(connector/'Code.js',(ROOT/'reporting/community-connector/Code.js').read_text().replace("getProperty('IMS_BASE_URL')||''","getProperty('IMS_BASE_URL')||"+json.dumps(base)))
    manifest=json.loads((ROOT/'reporting/community-connector/appsscript.json').read_text());manifest['urlFetchWhitelist']=[base+'/']
    write(connector/'appsscript.json',json.dumps(manifest,indent=2))
    write(out/'INSTALL-NEXT.md',f'''# Generated installation

1. Review runtime.env, operator-credentials.json and each private sgtm-settings.json; keep out of source control/client reports.
2. Fill required account env values and mount any approved Simpli.fi feed paths in jobs service. API and jobs share the durable database.
3. Run `docker compose -f compose.json up --build -d` from this directory. Install the generated Caddyfile with Caddy on the host and point DNS to the host.
4. Import dist/ims-http-client.tpl and dist/ims-ledger-forwarder.tpl into each server GTM container; enter generated settings and create the ims_touch trigger. Configure approved destination tags only if sGTM purchase forwarding is enabled.
5. Install the generated Shopify pixel in Customer Events, set analytics/marketing privacy requirements, and register paid/refund HTTPS webhooks at {base}/shopify/TENANT.
6. Paste looker-connector/Code.js and appsscript.json into Apps Script and deploy as a Community Connector. Configure each client data source using CLIENT token; agency tokens are refused.
7. Run the installed acceptance checklist. Do not enable old/new conversion senders for the same primary action simultaneously.

Browser/webhook credentials are separate. Google click-upload route requires eligible API access and an import conversion action; use the sGTM native Google Ads tag if click-upload access is unavailable.
''')
    if os.getuid()==0:
        for p in [out,*out.rglob('*')]:os.chown(p,uid,gid)
    return {'status':'generated','tenants':len(credentials),'jobs':len(jobs),'directory':str(out)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    with open(a.config) as f:config=json.load(f)
    print(json.dumps(configure(config,a.output)))
if __name__=='__main__':main()
