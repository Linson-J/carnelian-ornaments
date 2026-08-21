from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Category, CategoryTag, Product, ProductImage, CarouselItem, HomeTheme,
    HomeSection, HomeSectionCategory, HomeSectionProduct, Offer,
)


MAX_IMAGE_SIZE = 5 * 1024 * 1024


def first_primary_image(images):
    image_list = list(images)
    return next((image for image in image_list if image.is_primary), None) or (
        image_list[0] if image_list else None
    )


class ProductUploadImageField(serializers.ImageField):
    def to_internal_value(self, data):
        image = super().to_internal_value(data)
        if image.size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError('Each image must be 5MB or smaller.')
        return image


# ─── Category ─────────────────────────────────────────────────
class CategoryTagSerializer(serializers.ModelSerializer):
    category_count = serializers.SerializerMethodField()

    class Meta:
        model = CategoryTag
        fields = [
            'id', 'name', 'slug', 'is_system', 'is_active',
            'category_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['slug', 'is_system', 'category_count', 'created_at', 'updated_at']
        extra_kwargs = {
            'name': {'allow_blank': False},
            'is_active': {'required': False},
        }

    def get_category_count(self, obj):
        return obj.categories.count()


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField(read_only=True)
    tags = CategoryTagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=CategoryTag.objects.all(),
        many=True,
        write_only=True,
        required=False,
        source='tags',
    )

    class Meta:
        model  = Category
        fields = [
            'id', 'name', 'slug', 'image', 'image_url', 'description',
            'status', 'is_popular', 'tags', 'tag_ids',
            'product_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['slug', 'product_count', 'created_at', 'updated_at']
        extra_kwargs = {
            'image': {'required': False, 'allow_null': True},
            'description': {'required': False, 'allow_blank': True},
            'status': {'required': False},
            'is_popular': {'required': False},
        }

    def get_product_count(self, obj):
        return obj.products.count()

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url

    def validate_image(self, image):
        if image and image.size > MAX_IMAGE_SIZE:
            raise serializers.ValidationError('Image must be 5MB or smaller.')
        return image

    def validate_tag_ids(self, tags):
        inactive = [tag.name for tag in tags if not tag.is_active]
        if inactive:
            raise serializers.ValidationError(
                f"Inactive tags cannot be assigned: {', '.join(inactive)}."
            )
        return tags


# ─── Product Image ────────────────────────────────────────────
class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = ProductImage
        fields = ['id', 'image_url', 'is_primary', 'order']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


# ─── Product READ (full nested response) ─────────────────────
class ProductReadSerializer(serializers.ModelSerializer):
    category         = CategorySerializer(read_only=True)
    images           = ProductImageSerializer(many=True, read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    primary_image    = serializers.SerializerMethodField()

    class Meta:
        model  = Product
        fields = [
            'id', 'name', 'slug', 'description',
            'price', 'discount_price', 'discount_percent',
            'category', 'stock', 'status',
            'colors', 'offer',
            'primary_image', 'images',
            'created_at', 'updated_at',
        ]

    def get_primary_image(self, obj):
        img = first_primary_image(obj.images.all())
        if img:
            return ProductImageSerializer(img, context=self.context).data
        return None


# ─── Product WRITE (create / update) ─────────────────────────
class ProductWriteSerializer(serializers.ModelSerializer):
    # Accept multiple uploaded images at once
    uploaded_images = serializers.ListField(
        child=ProductUploadImageField(), write_only=True, required=False
    )
    # Which image id should be primary (optional)
    primary_image_id = serializers.IntegerField(write_only=True, required=False)
    removed_image_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model  = Product
        fields = [
            'name', 'description',
            'price', 'discount_price',
            'category', 'stock', 'status',
            'colors', 'offer',
            'uploaded_images', 'primary_image_id', 'removed_image_ids',
        ]
        extra_kwargs = {
            'name': {'allow_blank': False},
            'description': {'allow_blank': False},
            'price': {'min_value': Decimal('0.01')},
            'discount_price': {'min_value': Decimal('0.01')},
            'category': {'required': True, 'allow_null': False},
            'stock': {'min_value': 0},
        }

    def validate(self, data):
        price = data.get('price', getattr(self.instance, 'price', None))
        discount_price = data.get(
            'discount_price', getattr(self.instance, 'discount_price', None)
        )
        if discount_price is not None and price is not None and discount_price >= price:
            raise serializers.ValidationError({
                'discount_price': 'Discount price must be less than the original price.'
            })

        if not self.instance and not data.get('uploaded_images'):
            raise serializers.ValidationError({
                'uploaded_images': 'At least one product image is required.'
            })

        colors = data.get('colors')
        if colors is not None:
            if not isinstance(colors, list):
                raise serializers.ValidationError({'colors': 'Colors must be a list.'})
            cleaned_colors = []
            for color in colors:
                if not isinstance(color, str) or not color.strip():
                    raise serializers.ValidationError({
                        'colors': 'Every color must be a non-empty string.'
                    })
                cleaned = color.strip()
                if len(cleaned) > 50:
                    raise serializers.ValidationError({
                        'colors': 'Each color must be 50 characters or fewer.'
                    })
                if cleaned not in cleaned_colors:
                    cleaned_colors.append(cleaned)
            if len(cleaned_colors) > 20:
                raise serializers.ValidationError({
                    'colors': 'A product can have at most 20 colors.'
                })
            data['colors'] = cleaned_colors

        primary_image_id = data.get('primary_image_id')
        if primary_image_id and self.instance and not self.instance.images.filter(
            pk=primary_image_id
        ).exists():
            raise serializers.ValidationError({
                'primary_image_id': 'The selected image does not belong to this product.'
            })

        removed_image_ids = data.get('removed_image_ids', [])
        if removed_image_ids and self.instance:
            valid_ids = set(self.instance.images.filter(
                pk__in=removed_image_ids
            ).values_list('pk', flat=True))
            if valid_ids != set(removed_image_ids):
                raise serializers.ValidationError({
                    'removed_image_ids': 'One or more selected images do not belong to this product.'
                })
            remaining = self.instance.images.exclude(pk__in=removed_image_ids).count()
            remaining += len(data.get('uploaded_images', []))
            if remaining == 0:
                raise serializers.ValidationError({
                    'removed_image_ids': 'A product must keep at least one image.'
                })
            if primary_image_id in removed_image_ids:
                raise serializers.ValidationError({
                    'primary_image_id': 'The primary image cannot also be removed.'
                })
        return data

    @transaction.atomic
    def create(self, validated_data):
        images_data      = validated_data.pop('uploaded_images', [])
        validated_data.pop('primary_image_id', None)
        validated_data.pop('removed_image_ids', None)
        product = Product.objects.create(**validated_data)
        for i, img in enumerate(images_data):
            ProductImage.objects.create(
                product=product,
                image=img,
                is_primary=(i == 0),   # first uploaded = primary by default
                order=i,
            )
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        images_data      = validated_data.pop('uploaded_images', [])
        primary_image_id = validated_data.pop('primary_image_id', None)
        removed_image_ids = validated_data.pop('removed_image_ids', [])

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        # Append new images if provided
        existing_count = instance.images.count()
        for i, img in enumerate(images_data):
            ProductImage.objects.create(
                product=instance,
                image=img,
                is_primary=False,
                order=existing_count + i,
            )

        removed_primary = False
        for image in instance.images.filter(pk__in=removed_image_ids):
            removed_primary = removed_primary or image.is_primary
            if image.image:
                image.image.delete(save=False)
            image.delete()

        # Change primary image if requested
        if primary_image_id:
            pi = ProductImage.objects.get(pk=primary_image_id, product=instance)
            pi.is_primary = True
            pi.save()
        elif removed_primary:
            next_image = instance.images.first()
            if next_image:
                next_image.is_primary = True
                next_image.save()

        return instance


# ─── Carousel ─────────────────────────────────────────────────
MAX_CAROUSEL_IMAGE_SIZE = 8 * 1024 * 1024


class CarouselItemSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField(read_only=True)
    redirect_url = serializers.CharField(read_only=True)

    class Meta:
        model = CarouselItem
        fields = [
            'id', 'image', 'image_url', 'title', 'description', 'button_text',
            'redirect_type', 'customer_page', 'product', 'redirect_url',
            'order', 'is_active', 'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'image': {'required': False},
            'title': {'required': False, 'allow_blank': True},
            'description': {'required': False, 'allow_blank': True},
            'button_text': {'required': False, 'allow_blank': True},
            'redirect_type': {'required': False, 'allow_blank': True},
            'customer_page': {'required': False, 'allow_blank': True},
            'product': {'required': False, 'allow_null': True},
        }

    def _build_image_url(self, image_field):
        if not image_field:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(image_field.url)
        return image_field.url

    def get_image_url(self, obj):
        return self._build_image_url(obj.image)

    def validate(self, data):
        redirect_type = data.get(
            'redirect_type',
            getattr(self.instance, 'redirect_type', '') if self.instance else '',
        )
        customer_page = data.get(
            'customer_page',
            getattr(self.instance, 'customer_page', '') if self.instance else '',
        )
        product = data.get(
            'product',
            getattr(self.instance, 'product', None) if self.instance else None,
        )

        if not self.instance and not data.get('image'):
            raise serializers.ValidationError({
                'image': 'Desktop carousel image is required.',
            })

        if not redirect_type:
            data['customer_page'] = ''
            data['product'] = None
            return data

        if redirect_type == CarouselItem.RedirectType.PAGE and not customer_page:
            raise serializers.ValidationError({
                'customer_page': 'Select a customer page.',
            })
        if redirect_type == CarouselItem.RedirectType.PRODUCT and not product:
            raise serializers.ValidationError({
                'product': 'Select a product.',
            })
        if redirect_type == CarouselItem.RedirectType.PAGE:
            data['product'] = None
        elif redirect_type == CarouselItem.RedirectType.PRODUCT:
            data['customer_page'] = ''

        return data

    def validate_image(self, image):
        return self._validate_carousel_image(image)

    def _validate_carousel_image(self, image):
        if image and image.size > MAX_CAROUSEL_IMAGE_SIZE:
            raise serializers.ValidationError('Image must be 8MB or smaller.')
        return image


class HomeThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeTheme
        fields = [
            'primary_color', 'background_color', 'dark_background_color',
            'sale_background_color', 'text_color', 'muted_text_color',
            'surface_color', 'updated_at',
        ]
        read_only_fields = ['updated_at']

    def validate(self, data):
        for field, value in data.items():
            if field == 'updated_at':
                continue
            if not isinstance(value, str) or not value.startswith('#') or len(value) != 7:
                raise serializers.ValidationError({field: 'Use a hex color like #7c5357.'})
            try:
                int(value[1:], 16)
            except ValueError:
                raise serializers.ValidationError({field: 'Use a valid hex color.'})
        return data


class HomeSectionCategoryItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='category.id', read_only=True)
    name = serializers.CharField(source='category.name', read_only=True)
    slug = serializers.CharField(source='category.slug', read_only=True)
    image_url = serializers.SerializerMethodField()
    description = serializers.CharField(source='category.description', read_only=True)
    item_order = serializers.IntegerField(read_only=True)

    class Meta:
        model = HomeSectionCategory
        fields = ['id', 'name', 'slug', 'image_url', 'description', 'item_order']

    def get_image_url(self, obj):
        if not obj.category.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.category.image.url)
        return obj.category.image.url


class HomeSectionProductItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='product.id', read_only=True)
    name = serializers.CharField(source='product.name', read_only=True)
    slug = serializers.CharField(source='product.slug', read_only=True)
    price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    discount_price = serializers.DecimalField(source='product.discount_price', max_digits=10, decimal_places=2, read_only=True)
    discount_percent = serializers.IntegerField(source='product.discount_percent', read_only=True)
    status = serializers.CharField(source='product.status', read_only=True)
    offer = serializers.CharField(source='product.offer', read_only=True)
    category = CategorySerializer(source='product.category', read_only=True)
    primary_image = serializers.SerializerMethodField()
    images = ProductImageSerializer(source='product.images', many=True, read_only=True)
    item_order = serializers.IntegerField(read_only=True)

    class Meta:
        model = HomeSectionProduct
        fields = [
            'id', 'name', 'slug', 'price', 'discount_price', 'discount_percent',
            'status', 'offer', 'category', 'primary_image', 'images', 'item_order',
        ]

    def get_primary_image(self, obj):
        image = first_primary_image(obj.product.images.all())
        if image:
            return ProductImageSerializer(image, context=self.context).data
        return None


class HomeSectionSerializer(serializers.ModelSerializer):
    category_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
    )
    product_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
    )
    items = serializers.SerializerMethodField()
    selected_ids = serializers.SerializerMethodField()

    class Meta:
        model = HomeSection
        fields = [
            'id', 'title', 'section_type', 'display_order', 'is_visible',
            'category_ids', 'product_ids', 'selected_ids', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        section_type = data.get(
            'section_type',
            getattr(self.instance, 'section_type', None) if self.instance else None,
        )
        if section_type == HomeSection.SectionType.CATEGORIES and 'product_ids' in self.initial_data:
            raise serializers.ValidationError({'product_ids': 'Use category_ids for category sections.'})
        if section_type == HomeSection.SectionType.PRODUCTS and 'category_ids' in self.initial_data:
            raise serializers.ValidationError({'category_ids': 'Use product_ids for product sections.'})
        category_ids = data.get('category_ids')
        if category_ids is not None:
            unique_ids = list(dict.fromkeys(category_ids))
            found = Category.objects.filter(pk__in=unique_ids).count()
            if found != len(unique_ids):
                raise serializers.ValidationError({'category_ids': 'One or more categories do not exist.'})
            data['category_ids'] = unique_ids
        product_ids = data.get('product_ids')
        if product_ids is not None:
            unique_ids = list(dict.fromkeys(product_ids))
            found = Product.objects.filter(pk__in=unique_ids).count()
            if found != len(unique_ids):
                raise serializers.ValidationError({'product_ids': 'One or more products do not exist.'})
            data['product_ids'] = unique_ids
        return data

    def get_items(self, obj):
        if obj.section_type == HomeSection.SectionType.CATEGORIES:
            links = obj.category_links.select_related('category').filter(
                category__status=Category.Status.ACTIVE,
            )
            return HomeSectionCategoryItemSerializer(links, many=True, context=self.context).data
        links = obj.product_links.select_related('product', 'product__category').prefetch_related(
            'product__images',
        ).filter(product__status=Product.Status.AVAILABLE)
        return HomeSectionProductItemSerializer(links, many=True, context=self.context).data

    def get_selected_ids(self, obj):
        if obj.section_type == HomeSection.SectionType.CATEGORIES:
            return list(obj.category_links.order_by('item_order', 'id').values_list('category_id', flat=True))
        return list(obj.product_links.order_by('item_order', 'id').values_list('product_id', flat=True))

    def _sync_items(self, section, category_ids=None, product_ids=None):
        if category_ids is not None:
            section.category_links.all().delete()
            HomeSectionCategory.objects.bulk_create([
                HomeSectionCategory(section=section, category_id=pk, item_order=index)
                for index, pk in enumerate(category_ids)
            ])
        if product_ids is not None:
            section.product_links.all().delete()
            HomeSectionProduct.objects.bulk_create([
                HomeSectionProduct(section=section, product_id=pk, item_order=index)
                for index, pk in enumerate(product_ids)
            ])

    @transaction.atomic
    def create(self, validated_data):
        category_ids = validated_data.pop('category_ids', None)
        product_ids = validated_data.pop('product_ids', None)
        section = HomeSection.objects.create(**validated_data)
        self._sync_items(section, category_ids=category_ids, product_ids=product_ids)
        return section

    @transaction.atomic
    def update(self, instance, validated_data):
        category_ids = validated_data.pop('category_ids', None)
        product_ids = validated_data.pop('product_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        self._sync_items(instance, category_ids=category_ids, product_ids=product_ids)
        return instance


MAX_OFFER_IMAGE_SIZE = 8 * 1024 * 1024


class OfferSerializer(serializers.ModelSerializer):
    banner_image_url = serializers.SerializerMethodField(read_only=True)
    popup_image_url = serializers.SerializerMethodField(read_only=True)
    redirect_url = serializers.CharField(read_only=True)
    is_currently_active = serializers.BooleanField(read_only=True)
    countdown = serializers.SerializerMethodField(read_only=True)
    category_detail = CategorySerializer(source='category', read_only=True)
    product_detail = ProductReadSerializer(source='product', read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id', 'title', 'subtitle', 'description', 'banner_image',
            'banner_image_url', 'button_text', 'redirect_type', 'category',
            'category_detail', 'product', 'product_detail', 'customer_page',
            'external_url', 'redirect_url', 'display_priority_pc',
            'display_priority_mobile', 'status', 'start_at', 'end_at',
            'no_expiry', 'countdown', 'is_currently_active', 'show_as_popup',
            'display_on_home', 'display_on_offer_page', 'popup_title',
            'popup_description', 'popup_image', 'popup_image_url',
            'popup_button_text', 'popup_display_mode', 'show_close_button',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'subtitle': {'required': False, 'allow_blank': True},
            'banner_image': {'required': False},
            'button_text': {'required': False, 'allow_blank': True},
            'category': {'required': False, 'allow_null': True},
            'product': {'required': False, 'allow_null': True},
            'customer_page': {'required': False, 'allow_blank': True},
            'external_url': {'required': False, 'allow_blank': True},
            'display_priority_mobile': {'required': False, 'allow_null': True},
            'start_at': {'required': False, 'allow_null': True},
            'end_at': {'required': False, 'allow_null': True},
            'no_expiry': {'required': False},
            'show_as_popup': {'required': False},
            'display_on_home': {'required': False},
            'display_on_offer_page': {'required': False},
            'popup_title': {'required': False, 'allow_blank': True},
            'popup_description': {'required': False, 'allow_blank': True},
            'popup_image': {'required': False, 'allow_null': True},
            'popup_button_text': {'required': False, 'allow_blank': True},
            'popup_display_mode': {'required': False},
            'show_close_button': {'required': False},
        }

    def _build_image_url(self, image_field):
        if not image_field:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(image_field.url)
        return image_field.url

    def get_banner_image_url(self, obj):
        return self._build_image_url(obj.banner_image)

    def get_popup_image_url(self, obj):
        return self._build_image_url(obj.popup_image or obj.banner_image)

    def get_countdown(self, obj):
        if obj.no_expiry or not obj.end_at:
            return None
        remaining = max(int((obj.end_at - timezone.now()).total_seconds()), 0)
        days, rem = divmod(remaining, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        return {
            'days': days,
            'hours': hours,
            'minutes': minutes,
            'seconds': seconds,
            'total_seconds': remaining,
        }

    def validate_banner_image(self, image):
        return self._validate_offer_image(image)

    def validate_popup_image(self, image):
        return self._validate_offer_image(image)

    def _validate_offer_image(self, image):
        if image and image.size > MAX_OFFER_IMAGE_SIZE:
            raise serializers.ValidationError('Image must be 8MB or smaller.')
        return image

    def validate(self, data):
        redirect_type = data.get(
            'redirect_type',
            getattr(self.instance, 'redirect_type', None) if self.instance else None,
        )
        category = data.get('category', getattr(self.instance, 'category', None) if self.instance else None)
        product = data.get('product', getattr(self.instance, 'product', None) if self.instance else None)
        external_url = data.get('external_url', getattr(self.instance, 'external_url', '') if self.instance else '')
        customer_page = data.get('customer_page', getattr(self.instance, 'customer_page', '') if self.instance else '')
        no_expiry = data.get('no_expiry', getattr(self.instance, 'no_expiry', False) if self.instance else False)
        start_at = data.get('start_at', getattr(self.instance, 'start_at', None) if self.instance else None)
        end_at = data.get('end_at', getattr(self.instance, 'end_at', None) if self.instance else None)

        if not self.instance and not data.get('banner_image'):
            raise serializers.ValidationError({'banner_image': 'Offer banner image is required.'})
        if not redirect_type:
            raise serializers.ValidationError({'redirect_type': 'Select a redirect type.'})

        if redirect_type == Offer.RedirectType.CATEGORY:
            if not category:
                raise serializers.ValidationError({'category': 'Select a category.'})
            data['product'] = None
            data['external_url'] = ''
            data['customer_page'] = ''
        elif redirect_type == Offer.RedirectType.PRODUCT:
            if not product:
                raise serializers.ValidationError({'product': 'Select a product.'})
            data['category'] = None
            data['external_url'] = ''
            data['customer_page'] = ''
        elif redirect_type == Offer.RedirectType.EXTERNAL_URL:
            if not external_url:
                raise serializers.ValidationError({'external_url': 'Enter an external URL.'})
            data['category'] = None
            data['product'] = None
            data['customer_page'] = ''
        elif redirect_type == Offer.RedirectType.PAGE:
            if not customer_page:
                raise serializers.ValidationError({'customer_page': 'Select a page.'})
            data['category'] = None
            data['product'] = None
            data['external_url'] = ''

        if start_at and end_at and end_at <= start_at:
            raise serializers.ValidationError({'end_at': 'End date must be after start date.'})
        if no_expiry:
            data['end_at'] = None
        elif not end_at:
            raise serializers.ValidationError({'end_at': 'End date is required unless No Expiry is enabled.'})

        return data
