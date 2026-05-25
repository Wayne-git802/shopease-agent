import requests, json

r = requests.post('http://127.0.0.1:8000/users/register/', data={
    'username': 'diagtest',
    'email': 'diag@test.com',
    'password1': 'Test1234',
    'password2': 'Test1234',
    'role': 'customer',
}, allow_redirects=False)
print(f"Status: {r.status_code}")
print(f"Location: {r.headers.get('Location', 'none')}")
print(f"Body[:500]: {r.text[:500]}")
