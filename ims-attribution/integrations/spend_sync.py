"""Google + Meta daily campaign spend to canonical CSV. Python standard library only.
Use stable campaign IDs as campaign keys and in campaign UTMs; never mix labels/IDs.
Native Simpli.fi ingestion is intentionally not invented: use vendor CSV schema adapter.
"""
import argparse
import csv
import json
import os
import urllib.parse
import urllib.request

def request(url,headers=None,data=None):
    body=json.dumps(data).encode() if data is not None else None
    req=urllib.request.Request(url,data=body,headers=headers or {})
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)

def google(start,end):
    token=os.environ.get('GOOGLE_ADS_ACCESS_TOKEN')
    if not token:
        fields=urllib.parse.urlencode({'grant_type':'refresh_token','refresh_token':os.environ['GOOGLE_ADS_REFRESH_TOKEN'],
               'client_id':os.environ['GOOGLE_ADS_CLIENT_ID'],'client_secret':os.environ['GOOGLE_ADS_CLIENT_SECRET']}).encode()
        req=urllib.request.Request('https://oauth2.googleapis.com/token',data=fields,headers={'Content-Type':'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(req,timeout=45) as response:token=json.load(response)['access_token']
    version=os.environ['GOOGLE_ADS_API_VERSION']
    customer=os.environ['GOOGLE_ADS_CUSTOMER_ID'].replace('-','')
    headers={'Authorization':'Bearer '+token,
             'developer-token':os.environ['GOOGLE_ADS_DEVELOPER_TOKEN'],'Content-Type':'application/json'}
    if os.environ.get('GOOGLE_ADS_LOGIN_CUSTOMER_ID'):headers['login-customer-id']=os.environ['GOOGLE_ADS_LOGIN_CUSTOMER_ID'].replace('-','')
    query=("SELECT segments.date, campaign.id, customer.currency_code, metrics.cost_micros, metrics.impressions, metrics.clicks FROM campaign WHERE segments.date BETWEEN '"+start+"' AND '"+end+"'")
    pages=request('https://googleads.googleapis.com/'+version+'/customers/'+customer+'/googleAds:searchStream',headers,{'query':query})
    for page in pages:
        for r in page.get('results',[]):
            m=r['metrics']
            yield {'date':r['segments']['date'],'channel':'google_ads','campaign':r['campaign']['id'],
                   'currency':r['customer']['currencyCode'],'cost':str(int(m.get('costMicros',0))/1000000),
                   'impressions':m.get('impressions',0),'clicks':m.get('clicks',0)}

def meta(start,end):
    version=os.environ['META_API_VERSION'];account=os.environ['META_AD_ACCOUNT_ID'].removeprefix('act_')
    params={'fields':'date_start,campaign_id,account_currency,spend,impressions,clicks',
            'level':'campaign','time_increment':'1','limit':'500',
            'time_range':json.dumps({'since':start,'until':end})}
    url='https://graph.facebook.com/'+version+'/act_'+account+'/insights?'+urllib.parse.urlencode(params)
    headers={'Authorization':'Bearer '+os.environ['META_ACCESS_TOKEN']}
    while url:
        page=request(url,headers)
        for r in page.get('data',[]):
            yield {'date':r['date_start'],'channel':'meta','campaign':r['campaign_id'],
                   'currency':r['account_currency'],'cost':r['spend'],'impressions':r.get('impressions',0),'clicks':r.get('clicks',0)}
        # Rebuild paging query against a fixed vendor origin; never follow arbitrary URLs.
        after=page.get('paging',{}).get('cursors',{}).get('after')
        if page.get('paging',{}).get('next') and after:
            params['after']=after
            url='https://graph.facebook.com/'+version+'/act_'+account+'/insights?'+urllib.parse.urlencode(params)
        else:url=None

def main():
    from datetime import datetime
    p=argparse.ArgumentParser();p.add_argument('platform',choices=['google','meta']);p.add_argument('--start',required=True);p.add_argument('--end',required=True);p.add_argument('--out',required=True)
    a=p.parse_args()
    for value in [a.start,a.end]:datetime.strptime(value,'%Y-%m-%d')
    # Fetch completes before file replacement; failure never truncates a previous good CSV.
    rows=list((google if a.platform=='google' else meta)(a.start,a.end))
    with open(a.out+'.tmp','w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['date','channel','campaign','currency','cost','impressions','clicks']);w.writeheader();w.writerows(rows)
    os.replace(a.out+'.tmp',a.out)
    print(json.dumps({'platform':a.platform,'rows':len(rows)}))
if __name__=='__main__':main()
