import requests

# First get CSRF token
s = requests.Session()
r = s.get('http://127.0.0.1:8000/users/register/')
import re
csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
if csrf:
    token = csrf.group(1)
    print(f"CSRF: {token[:20]}...")
    
    r2 = s.post('http://127.0.0.1:8000/users/register/', data={
        'csrfmiddlewaretoken': token,
        'username': 'diagtest2',
        'email': 'diag2@test.com',
        'password': 'Test1234',
        'password_confirm': 'Test1234',
        'role': 'customer',
    })
    print(f"Status: {r2.status_code}")
    print(f"URL: {r2.url}")
    if r2.status_code == 200:
        if 'error' in r2.text.lower() or 'Error' in r2.text:
            # extract error
            m = re.search(r'class="error[^"]*">([^<]+)', r2.text) or re.search(r'alert[^>]*>([^<]+)', r2.text)
            if m: print(f"Error msg: {m.group(1)}")
    print(f"Body[:300]: {r2.text[:300]}")
else:
    print("No CSRF token found!")
    print(r.text[:500])
