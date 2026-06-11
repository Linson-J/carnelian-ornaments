from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ─── Existing AdminUser / LoginAttempt stay here ──────────────
# (keep your AdminUser and LoginAttempt models above this)


# ─── Category ─────────────────────────────────────────────────
class Category(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'

    name        = models.CharField(max_length=100, unique=True)
    slug        = models.SlugField(max_length=100, unique=True, blank=True)
    image       = models.ImageField(upload_to='categories/%Y/%m/', blank=True, null=True)
    description = models.TextField(blank=True)
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    is_popular  = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table  = 'shop_categories'
        ordering  = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.name)
            slug = base
            n = 1
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)


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
class CarouselItem(models.Model):
    class RedirectType(models.TextChoices):
        PAGE = 'page', 'Page'
        PRODUCT = 'product', 'Product'

    class CustomerPage(models.TextChoices):
        HOME = '/', 'Home'
        SHOP = '/#collection', 'Shop'
        NEW_ARRIVALS = '/#new-arrivals', 'New Arrivals'
        COLLECTIONS = '/#collections', 'Collections'
        WISHLIST = '/#wishlist', 'Wishlist'
        CART = '/#cart', 'Cart'
        PROFILE = '/#profile', 'Profile'

    image = models.ImageField(upload_to='carousel/%Y/%m/', help_text='Desktop / PC carousel image.')
    mobile_image = models.ImageField(
        upload_to='carousel/%Y/%m/', blank=True, null=True,
        help_text='Optional mobile carousel image. Falls back to desktop image when empty.',
    )
    title = models.CharField(max_length=150, blank=True, default='')
    description = models.TextField(max_length=500, blank=True, default='')
    button_text = models.CharField(max_length=50, blank=True, default='')
    redirect_type = models.CharField(
        max_length=10, choices=RedirectType.choices, blank=True, default=''
    )
    customer_page = models.CharField(
        max_length=50, choices=CustomerPage.choices, blank=True
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='carousel_items',
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_carousel_items'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title or f'Carousel item {self.pk or ""}'.strip()

    @property
    def has_overlay_content(self):
        return bool(self.title or self.description or self.button_text)

    @property
    def mobile_display_image(self):
        return self.mobile_image or self.image

    def clean(self):
        if not self.redirect_type:
            self.customer_page = ''
            self.product = None
            return

        errors = {}
        if self.redirect_type == self.RedirectType.PAGE:
            if not self.customer_page:
                errors['customer_page'] = 'Select a customer page.'
            self.product = None
        elif self.redirect_type == self.RedirectType.PRODUCT:
            if not self.product_id:
                errors['product'] = 'Select a product.'
            self.customer_page = ''
        if errors:
            raise ValidationError(errors)

    @property
    def redirect_url(self):
        if not self.redirect_type:
            return ''
        if self.redirect_type == self.RedirectType.PRODUCT and self.product:
            return f'/products/{self.product.slug}/'
        return self.customer_page or '/'


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


class HomeTheme(models.Model):
    primary_color = models.CharField(max_length=7, default='#7c5357')
    background_color = models.CharField(max_length=7, default='#fffdfa')
    dark_background_color = models.CharField(max_length=7, default='#030303')
    sale_background_color = models.CharField(max_length=7, default='#e8b2bb')
    text_color = models.CharField(max_length=7, default='#1a1c1a')
    muted_text_color = models.CharField(max_length=7, default='#504444')
    surface_color = models.CharField(max_length=7, default='#ffffff')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_home_theme'
        verbose_name = 'home theme'
        verbose_name_plural = 'home theme'

    def __str__(self):
        return 'Home theme'

    @classmethod
    def current(cls):
        theme, _ = cls.objects.get_or_create(pk=1)
        return theme


# ─── After saving, run these two commands ────────────────────
# python manage.py makemigrations shop
# python manage.py migrate
