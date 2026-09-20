import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import (
    AdminUser,
    CarouselItem,
    Category,
    CategoryTag,
    HomeSection,
    HomeSectionCategory,
    HomeSectionProduct,
    HomeTheme,
    GSTConfig,
    GSTRate,
    StoreAddressSettings,
    LoginAttempt,
    NewsletterSubscription,
    Product,
    ProductImage,
    DeliveryZone,
    DeliveryConfig,
    Order,
    OrderItem,
    PaymentTransaction,
    PaymentWebhookEvent,
    UserProfile,
    ContactMessage,
    Coupon,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'is_popular', 'created_at')
    list_filter = ('status', 'is_popular', 'tags')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('tags',)


@admin.register(CategoryTag)
class CategoryTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_system', 'is_active')
    list_filter = ('is_system', 'is_active')
    search_fields = ('name', 'slug')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'discount_price', 'stock', 'status')
    list_filter = ('status', 'category')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (ProductImageInline,)


@admin.register(CarouselItem)
class CarouselItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'redirect_type', 'product', 'order', 'is_active')
    list_filter = ('is_active', 'redirect_type')
    search_fields = ('title', 'description', 'button_text')


@admin.register(HomeTheme)
class HomeThemeAdmin(admin.ModelAdmin):
    list_display = ('id', 'primary_color', 'background_color', 'updated_at')


class HomeSectionCategoryInline(admin.TabularInline):
    model = HomeSectionCategory
    extra = 0


class HomeSectionProductInline(admin.TabularInline):
    model = HomeSectionProduct
    extra = 0


@admin.register(HomeSection)
class HomeSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'section_type', 'display_order', 'is_visible')
    list_filter = ('section_type', 'is_visible')
    search_fields = ('title',)
    inlines = (HomeSectionCategoryInline, HomeSectionProductInline)


@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_active', 'last_login', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('username', 'email')


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('username', 'ip_address', 'success', 'attempted_at')
    list_filter = ('success', 'attempted_at')
    search_fields = ('username', 'ip_address')


@admin.action(description='Export selected subscriptions as CSV')
def export_newsletter_subscriptions(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="newsletter_subscriptions.csv"'
    writer = csv.writer(response)
    writer.writerow(['email', 'subscribed_at', 'is_active'])
    for subscription in queryset.order_by('-subscribed_at'):
        writer.writerow([
            subscription.email,
            subscription.subscribed_at.isoformat(),
            subscription.is_active,
        ])
    return response


@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'subscribed_at')
    list_filter = ('is_active', 'subscribed_at')
    search_fields = ('email',)
    ordering = ('-subscribed_at',)
    actions = (export_newsletter_subscriptions,)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['subscription_count'] = self.model.objects.count()
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ('country', 'state', 'county', 'city', 'is_active')
    list_filter = ('country', 'state', 'is_active')
    search_fields = ('state', 'county', 'city')


@admin.register(DeliveryConfig)
class DeliveryConfigAdmin(admin.ModelAdmin):
    list_display = ('fee_type', 'base_fee', 'free_threshold')


@admin.register(GSTRate)
class GSTRateAdmin(admin.ModelAdmin):
    list_display = ('name', 'percentage', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(GSTConfig)
class GSTConfigAdmin(admin.ModelAdmin):
    list_display = ('enabled', 'seller_state', 'default_rate', 'pricing_mode', 'updated_at')


@admin.register(StoreAddressSettings)
class StoreAddressSettingsAdmin(admin.ModelAdmin):
    list_display = ('sender_name', 'contact_email', 'contact_phone', 'whatsapp_number', 'cod_enabled', 'cod_extra_charge', 'updated_at')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'full_name', 'total', 'cod_extra_charge', 'status', 'payment_method', 'payment_status', 'phonepe_transaction_id', 'created_at')
    list_filter = ('status', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('full_name', 'phone', 'street_address', 'city', 'phonepe_merchant_order_id', 'phonepe_transaction_id')
    inlines = (OrderItemInline,)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.payment_method.lower() == 'phonepe' and obj.payment_status == Order.PaymentStatus.PAID:
            readonly.extend([
                'payment_status',
                'payment_method',
                'payment_id',
                'phonepe_merchant_order_id',
                'phonepe_order_id',
                'phonepe_transaction_id',
                'phonepe_payment_state',
                'phonepe_response_code',
            ])
        return readonly


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('merchant_order_id', 'order', 'provider', 'amount_paise', 'status', 'provider_state', 'provider_transaction_id', 'created_at')
    list_filter = ('provider', 'status', 'provider_state', 'created_at')
    search_fields = ('merchant_order_id', 'provider_order_id', 'provider_transaction_id', 'order__id', 'order__full_name')
    readonly_fields = ('request_payload', 'response_payload', 'created_at', 'updated_at', 'verified_at')

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.provider == PaymentTransaction.Provider.PHONEPE and obj.status == PaymentTransaction.Status.SUCCESS:
            return [field.name for field in self.model._meta.fields]
        return super().get_readonly_fields(request, obj)


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'merchant_order_id', 'event_id', 'processed', 'received_at', 'processed_at')
    list_filter = ('provider', 'processed', 'received_at')
    search_fields = ('merchant_order_id', 'event_id', 'payload_hash')
    readonly_fields = ('payload', 'payload_hash', 'received_at', 'processed_at')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'city', 'state', 'country', 'postal_code')
    search_fields = ('user__email', 'phone', 'city', 'state', 'postal_code')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'min_purchase', 'valid_until', 'used_count', 'usage_limit', 'is_active')
    list_filter = ('discount_type', 'is_active', 'created_at')
    search_fields = ('code',)
    ordering = ('-created_at',)



