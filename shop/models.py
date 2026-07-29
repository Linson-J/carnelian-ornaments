from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .utils import unique_slug


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
    tags        = models.ManyToManyField(
        'CategoryTag',
        blank=True,
        related_name='categories',
        db_table='shop_category_tag_assignments',
    )
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
            self.slug = unique_slug(self, self.name, Category.objects)
        super().save(*args, **kwargs)


# ─── Product ──────────────────────────────────────────────────
class CategoryTag(models.Model):
    POPULAR_SLUG = 'popular-category'
    TRENDING_SLUG = 'trending-category'
    SYSTEM_SLUGS = (POPULAR_SLUG, TRENDING_SLUG)

    name       = models.CharField(max_length=100, unique=True)
    slug       = models.SlugField(max_length=100, unique=True, blank=True)
    is_system  = models.BooleanField(default=False)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_category_tags'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name, CategoryTag.objects)
        if self.slug in self.SYSTEM_SLUGS:
            self.is_system = True
        super().save(*args, **kwargs)

    @classmethod
    def ensure_defaults(cls):
        defaults = [
            ('Popular Category', cls.POPULAR_SLUG),
            ('Trending Category', cls.TRENDING_SLUG),
        ]
        for name, slug in defaults:
            cls.objects.update_or_create(
                slug=slug,
                defaults={'name': name, 'is_system': True, 'is_active': True},
            )


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
            self.slug = unique_slug(self, self.name, Product.objects)
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


class Offer(models.Model):
    class RedirectType(models.TextChoices):
        CATEGORY = 'category', 'Category'
        PRODUCT = 'product', 'Product'
        EXTERNAL_URL = 'external_url', 'External URL'
        PAGE = 'page', 'Page'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'

    class PopupDisplayMode(models.TextChoices):
        ONCE = 'once', 'Display once per user'
        EVERY_VISIT = 'every_visit', 'Display every visit'

    class CustomerPage(models.TextChoices):
        HOME = '/', 'Home'
        SHOP = '/#collection', 'Shop'
        NEW_ARRIVALS = '/#new-arrivals', 'New Arrivals'
        COLLECTIONS = '/#collections', 'Collections'
        CART = '/#cart', 'Cart'

    title = models.CharField(max_length=160)
    subtitle = models.CharField(max_length=180, blank=True, default='')
    description = models.TextField()
    banner_image = models.ImageField(upload_to='offers/%Y/%m/')
    button_text = models.CharField(max_length=60, default='Shop Now')
    redirect_type = models.CharField(max_length=20, choices=RedirectType.choices)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='offers',
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='offers',
    )
    customer_page = models.CharField(
        max_length=60, choices=CustomerPage.choices, blank=True, default='',
    )
    external_url = models.URLField(blank=True, default='')
    display_priority_pc = models.PositiveIntegerField(default=10)
    display_priority_mobile = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    no_expiry = models.BooleanField(default=False)
    show_as_popup = models.BooleanField(default=False)
    display_on_home = models.BooleanField(default=True)
    display_on_offer_page = models.BooleanField(default=True)
    popup_title = models.CharField(max_length=160, blank=True, default='')
    popup_description = models.TextField(blank=True, default='')
    popup_image = models.ImageField(upload_to='offers/popup/%Y/%m/', null=True, blank=True)
    popup_button_text = models.CharField(max_length=60, blank=True, default='')
    popup_display_mode = models.CharField(
        max_length=20, choices=PopupDisplayMode.choices, default=PopupDisplayMode.ONCE,
    )
    show_close_button = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_offers'
        ordering = ['display_priority_pc', 'id']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.show_as_popup:
            Offer.objects.filter(show_as_popup=True).exclude(pk=self.pk).update(show_as_popup=False)
        super().save(*args, **kwargs)

    @property
    def is_currently_active(self):
        now = timezone.now()
        if self.status != self.Status.ACTIVE:
            return False
        if self.start_at and self.start_at > now:
            return False
        if not self.no_expiry and self.end_at and self.end_at < now:
            return False
        if not self.no_expiry and not self.end_at:
            return False
        return True

    @property
    def redirect_url(self):
        if self.redirect_type == self.RedirectType.CATEGORY and self.category:
            return f'/categories/{self.category.slug}/'
        if self.redirect_type == self.RedirectType.PRODUCT and self.product:
            return f'/products/{self.product.slug}/'
        if self.redirect_type == self.RedirectType.EXTERNAL_URL:
            return self.external_url
        if self.redirect_type == self.RedirectType.PAGE:
            return self.customer_page or '/'
        return '/'


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


class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'shop_newsletter_subscriptions'
        ordering = ['-subscribed_at']

    def __str__(self):
        return self.email


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


class HomeSection(models.Model):
    class SectionType(models.TextChoices):
        CATEGORIES = 'categories', 'Categories'
        PRODUCTS = 'products', 'Products'

    DEFAULT_SECTIONS = (
        ('Popular Categories', SectionType.CATEGORIES, 10),
        ('Trending Categories', SectionType.CATEGORIES, 20),
        ('New Arrivals', SectionType.PRODUCTS, 30),
        ('Trending Products', SectionType.PRODUCTS, 40),
        ('Featured Products', SectionType.PRODUCTS, 50),
        ('Best Sellers', SectionType.PRODUCTS, 60),
    )

    title = models.CharField(max_length=120)
    section_type = models.CharField(max_length=20, choices=SectionType.choices)
    display_order = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    categories = models.ManyToManyField(
        Category,
        through='HomeSectionCategory',
        blank=True,
        related_name='home_sections',
    )
    products = models.ManyToManyField(
        Product,
        through='HomeSectionProduct',
        blank=True,
        related_name='home_sections',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'shop_home_sections'
        ordering = ['display_order', 'id']

    def __str__(self):
        return self.title

    @classmethod
    def ensure_defaults(cls):
        for title, section_type, display_order in cls.DEFAULT_SECTIONS:
            cls.objects.get_or_create(
                title=title,
                defaults={
                    'section_type': section_type,
                    'display_order': display_order,
                    'is_visible': True,
                },
            )


class HomeSectionCategory(models.Model):
    section = models.ForeignKey(HomeSection, on_delete=models.CASCADE, related_name='category_links')
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    item_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'shop_home_section_categories'
        ordering = ['item_order', 'id']
        unique_together = ('section', 'category')


class HomeSectionProduct(models.Model):
    section = models.ForeignKey(HomeSection, on_delete=models.CASCADE, related_name='product_links')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    item_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'shop_home_section_products'
        ordering = ['item_order', 'id']
        unique_together = ('section', 'product')

