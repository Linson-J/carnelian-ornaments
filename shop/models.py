from django.db import models
from django.utils import timezone


# ─── Existing AdminUser / LoginAttempt stay here ──────────────
# (keep your AdminUser and LoginAttempt models above this)


# ─── Category ─────────────────────────────────────────────────
class Category(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    slug       = models.SlugField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table  = 'shop_categories'
        ordering  = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


# ─── Product ──────────────────────────────────────────────────
class Product(models.Model):

    class Status(models.TextChoices):
        AVAILABLE   = 'available',   'Available'
        OUT_OF_STOCK = 'out_of_stock', 'Out of Stock'
        DISCONTINUED = 'discontinued', 'Discontinued'

    name           = models.CharField(max_length=255)
    slug           = models.SlugField(max_length=255, unique=True, blank=True)
    description    = models.TextField()
    price          = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    category       = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    stock          = models.PositiveIntegerField(default=0)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    colors         = models.JSONField(default=list, blank=True)   # e.g. ["red","blue","black"]
    offer          = models.CharField(max_length=255, blank=True) # e.g. "10% off this weekend"
    created_at     = models.DateTimeField(default=timezone.now)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_products'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def discount_percent(self):
        if self.discount_price and self.price > 0:
            return round((1 - float(self.discount_price) / float(self.price)) * 100)
        return 0

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.name)
            slug = base
            n = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


# ─── Product Images (gallery) ─────────────────────────────────
class ProductImage(models.Model):
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image      = models.ImageField(upload_to='products/%Y/%m/')
    is_primary = models.BooleanField(default=False)
    order      = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'shop_product_images'
        ordering = ['order', 'id']

    def save(self, *args, **kwargs):
        # Only one image per product can be primary
        if self.is_primary:
            ProductImage.objects.filter(
                product=self.product, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

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