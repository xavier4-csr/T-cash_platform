import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

phone = '+254700000000'
password = 'superuser123'

if not User.objects.filter(phone_number=phone).exists():
    User.objects.create_superuser(phone_number=phone, password=password)
    print(f"Superuser created: Phone={phone}, Password={password}")
else:
    # update password
    user = User.objects.get(phone_number=phone)
    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print(f"Superuser updated: Phone={phone}, Password={password}")
