#!/usr/bin/env python
import os
import sys

# 添加项目路径
sys.path.insert(0, r'C:\Users\admin\Desktop\DBMS Project\mysite')
..\\..\\backend
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

import django
django.setup()

from django.core.management import call_command

print("=== 1. 生成迁移文件 ===")
call_command('makemigrations', 'users', verbosity=2)

print("\n=== 2. 执行迁移 ===")
call_command('migrate', 'users', verbosity=2)

print("\n=== 完成 ===")
