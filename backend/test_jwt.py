import os
import sys
sys.path.insert(0, r'C:\Users\admin\Desktop\DBMS Project\mysite')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

import django
django.setup()

from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User

# 测试用户 1233
try:
    user = User.objects.get(username='1233')
    print(f'User found: {user.username}')
    pwd_check = user.check_password('Test1234')
    print(f'Password check Test1234: {pwd_check}')

    if pwd_check:
        # 生成 JWT token
        refresh = RefreshToken.for_user(user)
        print('JWT Token generated successfully!')
        print('Access:', str(refresh.access_token)[:50] + '...')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
