"""Synthetic end-to-end demonstration; no network requests or real credentials."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ims.core import Store

with tempfile.TemporaryDirectory() as directory:
    s=Store(directory+'/demo.sqlite3');s.create_tenant('demo')
    s.touch('demo',{'event_id':'landing','visitor_id':'visitor','source':'google','medium':'cpc','campaign':'12345','analytics_consent':True,'ts':'2026-10-01T12:00:00Z'},trusted=True)
    s.order('demo',{'order_id':'verified-order','visitor_id':'visitor','ts':'2026-10-01T12:10:00Z','currency':'USD','revenue':'6000'})
    s.spend('demo',[{'date':'2026-10-01','channel':'google_ads','campaign':'12345','currency':'USD','cost':'1000','impressions':100000,'clicks':1000}])
    s.markup('demo','*','2026-01-01',10000)
    print('CLIENT-SAFE REPORT: $1,000 vendor cost becomes $2,000 media cost; ROAS = 3')
    print(json.dumps(s.report('demo','2026-10-01','2026-10-31'),indent=2))
    print('AGENCY REPORT: additional private cost/margin fields')
    print(json.dumps(s.report('demo','2026-10-01','2026-10-31',agency=True),indent=2))
