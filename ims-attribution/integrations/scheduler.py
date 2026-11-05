"""Container scheduler: one protected supervised pipeline; no cron installation needed."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--interval',type=int,default=300);a=p.parse_args()
    if a.interval<60:raise ValueError('Minimum schedule is 60 seconds')
    while True:
        result=subprocess.run([sys.executable,'-m','integrations.run_pipeline','--config',a.config,'--lock','/data/pipeline.lock'],capture_output=True)
        # No raw exception output: API tokens/URLs could be present in third-party errors.
        print(json.dumps({'pipeline_status':'succeeded' if result.returncode==0 else 'failed','time':int(time.time())}),flush=True)
        time.sleep(a.interval)
if __name__=='__main__':main()
