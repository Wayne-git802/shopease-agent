import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
import sys; sys.path.insert(0, 'C:\\Users\\admin\\Desktop\\shop_agent\\backend')
django.setup()
from users.models import User
try:
    u = User.objects.get(username='testbuyer99')
    print(f"User: {u.username}, active: {u.is_active}, id: {u.id}")
except User.DoesNotExist:
    print("User NOT created!")

# Check latest users
print("\nLast 5 users:")
for u in User.objects.order_by('-id')[:5]:
    print(f"  {u.id}: {u.username} (active={u.is_active})")
