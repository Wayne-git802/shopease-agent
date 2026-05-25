import os, sys, time
sys.path.insert(0, r'C:\Users\admin\Desktop\shop_agent\backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
import django
django.setup()

print("Importing orchestrator...", flush=True)
t0 = time.time()
from agents.graph.orchestrator import run
print(f"Orchestrator imported in {time.time()-t0:.1f}s", flush=True)

print("Running graph with simple query...", flush=True)
t0 = time.time()
try:
    result = run(query='hello', user_id=1, session_id='diag-test')
    print(f"Result ({time.time()-t0:.1f}s): ui_state={result.get('ui_state')}, intent={result.get('intent')}, reply={result.get('reply','')[:80]}", flush=True)
except Exception as e:
    print(f"Error after {time.time()-t0:.1f}s: {type(e).__name__}: {e}", flush=True)
