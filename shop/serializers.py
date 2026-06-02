from rest_framework import serializers
from .models import Category, Product, ProductImage


# ─── Category ─────────────────────────────────────────────────
class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model  = Category
        fields = ['id', 'name', 'slug', 'product_count']

    def get_product_count(self, obj):
        return obj.products.count()


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
        img = obj.images.filter(is_primary=True).first() \
              or obj.images.first()
        if img:
            return ProductImageSerializer(img, context=self.context).data
        return None


# ─── Product WRITE (create / update) ─────────────────────────
class ProductWriteSerializer(serializers.ModelSerializer):
    # Accept multiple uploaded images at once
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, required=False
    )
    # Which image id should be primary (optional)
    primary_image_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model  = Product
        fields = [
            'name', 'description',
            'price', 'discount_price',
            'category', 'stock', 'status',
            'colors', 'offer',
            'uploaded_images', 'primary_image_id',
        ]

    def validate_discount_price(self, value):
        price = self.initial_data.get('price') or (
            self.instance.price if self.instance else None
        )
        if value and price and float(value) >= float(price):
            raise serializers.ValidationError(
                'Discount price must be less than the original price.'
            )
        return value

    def validate(self, data):
        # On create, at least one image is required
        if not self.instance:
            if not data.get('uploaded_images'):
                raise serializers.ValidationError(
                    {'uploaded_images': 'At least one product image is required.'}
                )
        return data

    def create(self, validated_data):
        images_data      = validated_data.pop('uploaded_images', [])
        primary_image_id = validated_data.pop('primary_image_id', None)
        product = Product.objects.create(**validated_data)
        for i, img in enumerate(images_data):
            ProductImage.objects.create(
                product=product,
                image=img,
                is_primary=(i == 0),   # first uploaded = primary by default
                order=i,
            )
        return product

    def update(self, instance, validated_data):
        images_data      = validated_data.pop('uploaded_images', [])
        primary_image_id = validated_data.pop('primary_image_id', None)

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

        # Change primary image if requested
        if primary_image_id:
            try:
                pi = ProductImage.objects.get(pk=primary_image_id, product=instance)
                pi.is_primary = True
                pi.save()
            except ProductImage.DoesNotExist:
                pass

        return instance