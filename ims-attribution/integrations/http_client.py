"""Bounded vendor requests with no redirects, credential logging or infinite retry."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

class VendorError(Exception):
    def __init__(self,status,retryable=False):
        self.status,self.retryable=status,retryable
        super().__init__('Vendor request failed')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None

def call(url,headers=None,body=None,method=None,retries=2):
    if urllib.parse.urlsplit(url).scheme!='https':raise ValueError('HTTPS required')
    raw=json.dumps(body,separators=(',',':')).encode() if body is not None else None
    headers={**(headers or {})}
    if raw is not None:headers.setdefault('Content-Type','application/json')
    for attempt in range(retries+1):
        try:
            req=urllib.request.Request(url,data=raw,headers=headers,method=method)
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as response:
                content=response.read(5*1024*1024+1)
                if len(content)>5*1024*1024:raise VendorError(413)
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as error:
            retryable=error.code==429 or error.code>=500
            if not retryable or attempt==retries:raise VendorError(error.code,retryable) from None
        except (urllib.error.URLError,TimeoutError):
            if attempt==retries:raise VendorError(0,True) from None
        time.sleep(min(4,2**attempt))

def oauth_refresh(prefix):
    import os
    if os.environ.get(prefix+'_ACCESS_TOKEN'):return os.environ[prefix+'_ACCESS_TOKEN']
    raw=urllib.parse.urlencode({'grant_type':'refresh_token','refresh_token':os.environ[prefix+'_REFRESH_TOKEN'],
        'client_id':os.environ[prefix+'_CLIENT_ID'],'client_secret':os.environ[prefix+'_CLIENT_SECRET']}).encode()
    req=urllib.request.Request('https://oauth2.googleapis.com/token',data=raw,
        headers={'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as response:return json.load(response)['access_token']
