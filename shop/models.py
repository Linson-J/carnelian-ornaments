from django.db import models
from django.utils import timezone


# ─── Existing model ───────────────────────────────────────────
class Product(models.Model):
    name        = models.CharField(max_length=255)
    price       = models.FloatField()
    description = models.TextField()

    def __str__(self):
        return self.name


# ─── Admin auth models ────────────────────────────────────────
class AdminUser(models.Model):
    username   = models.CharField(max_length=50, unique=True)
    email      = models.EmailField(unique=True)
    password   = models.CharField(max_length=256)   # bcrypt hash
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'shop_admin_users'

    def __str__(self):
        return self.username


class LoginAttempt(models.Model):
    username     = models.CharField(max_length=50)
    ip_address   = models.GenericIPAddressField()
    attempted_at = models.DateTimeField(auto_now_add=True)
    success      = models.BooleanField(default=False)

    class Meta:
        db_table = 'shop_login_attempts'


# ─── After saving, run these two commands ────────────────────
# python manage.py makemigrations shop
# python manage.py migrate