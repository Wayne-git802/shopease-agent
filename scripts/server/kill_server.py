import subprocess

# Use wmic to get PIDs on port 8000
out = subprocess.check_output(
    'wmic process where "CommandLine like \'%runserver%\' and CommandLine like \'%8000%\'" get ProcessId',
    shell=True, text=True, errors='replace'
)
pids = [line.strip() for line in out.split('\n') if line.strip().isdigit()]
print(f"runserver PIDs: {pids}")

for pid in pids:
    code = subprocess.call(f'taskkill /F /PID {pid}', shell=True, 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  PID {pid}: exit={code}")

# Also kill anything on port 8000
import os
out2 = subprocess.check_output('netstat -ano', shell=True, text=True, errors='replace')
for line in out2.split('\n'):
    if ':8000' in line and 'LISTENING' in line:
        pid = line.strip().split()[-1]
        print(f"Port 8000 leftover PID: {pid} — force kill")
        os.system(f'taskkill /F /PID {pid} >nul 2>&1 &')

print("Done cleaning")
