from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    CarouselItem,
    Category,
    CategoryTag,
    HomeSection,
    HomeTheme,
    Offer,
    Product,
    ProductImage,
)
from .serializers import (
    CarouselItemSerializer,
    CategorySerializer,
    CategoryTagSerializer,
    HomeSectionSerializer,
    HomeThemeSerializer,
    OfferSerializer,
    ProductImageSerializer,
    ProductReadSerializer,
    ProductUploadImageField,
    ProductWriteSerializer,
)


def success(data=None, msg='Success', code=200):
    return Response({'success': True, 'message': msg, 'data': data}, status=code)


def error(msg='Error', errors=None, code=400):
    return Response({'success': False, 'message': msg, 'errors': errors}, status=code)


def parse_decimal_filter(value, field_name):
    if value in (None, ''):
        return None, None
    try:
        return Decimal(value), None
    except (InvalidOperation, TypeError):
        return None, {field_name: 'Enter a valid decimal value.'}


class AdminWritePermission(BasePermission):
    message = 'Admin login is required for this operation.'

    def has_permission(self, request, view):
        return (
            request.method in SAFE_METHODS
            or request.session.get('admin_authenticated') is True
        )


# ══════════════════════════════════════════════════════════════
# CATEGORY  —  /api/categories/
# ══════════════════════════════════════════════════════════════

def _sync_popular_flag(category):
    has_popular_tag = category.tags.filter(
        slug=CategoryTag.POPULAR_SLUG,
        is_active=True,
    ).exists()
    if category.is_popular != has_popular_tag:
        category.is_popular = has_popular_tag
        category.save(update_fields=['is_popular', 'updated_at'])


def _sync_legacy_popular_tag(category):
    popular = CategoryTag.objects.filter(slug=CategoryTag.POPULAR_SLUG).first()
    if not popular:
        return
    if category.is_popular and popular.is_active:
        category.tags.add(popular)
    else:
        category.tags.remove(popular)


class CategoryTagListCreateView(APIView):
    permission_classes = [AdminWritePermission]

    def get(self, request):
        CategoryTag.ensure_defaults()
        qs = CategoryTag.objects.prefetch_related('categories')
        active = request.query_params.get('active')
        if active in ('true', '1', 'yes'):
            qs = qs.filter(is_active=True)
        elif active in ('false', '0', 'no'):
            qs = qs.filter(is_active=False)
        return success(CategoryTagSerializer(qs, many=True).data)

    def post(self, request):
        s = CategoryTagSerializer(data=request.data)
        if s.is_valid():
            tag = s.save()
            return success(CategoryTagSerializer(tag).data, 'Category tag created', 201)
        return error('Validation failed', s.errors)


class CategoryTagDetailView(APIView):
    permission_classes = [AdminWritePermission]

    def get(self, request, pk):
        tag = get_object_or_404(CategoryTag, pk=pk)
        return success(CategoryTagSerializer(tag).data)

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        tag = get_object_or_404(CategoryTag, pk=pk)
        s = CategoryTagSerializer(tag, data=request.data, partial=True)
        if s.is_valid():
            updated = s.save()
            if not updated.is_active:
                Category.objects.filter(tags=updated).update(is_popular=False)
            return success(CategoryTagSerializer(updated).data, 'Category tag updated')
        return error('Validation failed', s.errors)

    def delete(self, request, pk):
        tag = get_object_or_404(CategoryTag, pk=pk)
        if tag.is_system:
            return error('System tags cannot be deleted.', code=400)
        tag.delete()
        return success(msg='Category tag deleted')


class CategoryListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]
    """
    GET  /api/categories/       → list all categories
    POST /api/categories/       → create category
    """
    def get(self, request):
        CategoryTag.ensure_defaults()
        cats = Category.objects.prefetch_related('tags')
        status_f = request.query_params.get('status')
        if status_f:
            cats = cats.filter(status=status_f)
        tag_slug = request.query_params.get('tag') or request.query_params.get('tag_slug')
        if tag_slug:
            cats = cats.filter(tags__slug=tag_slug, tags__is_active=True)
        popular_f = request.query_params.get('popular')
        if popular_f in ('true', '1', 'yes'):
            cats = cats.filter(tags__slug=CategoryTag.POPULAR_SLUG, tags__is_active=True)
        elif popular_f in ('false', '0', 'no'):
            cats = cats.exclude(tags__slug=CategoryTag.POPULAR_SLUG, tags__is_active=True)
        cats = cats.distinct()
        return success(CategorySerializer(cats, many=True, context={'request': request}).data)

    def post(self, request):
        CategoryTag.ensure_defaults()
        s = CategorySerializer(data=request.data, context={'request': request})
        if s.is_valid():
            category = s.save()
            if 'is_popular' in request.data and 'tag_ids' not in request.data:
                _sync_legacy_popular_tag(category)
            _sync_popular_flag(category)
            s = CategorySerializer(category, context={'request': request})
            return success(s.data, 'Category created', 201)
        return error('Validation failed', s.errors)


class CategoryDetailView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]
    """
    GET    /api/categories/<id>/  → single category
    PUT    /api/categories/<id>/  → update
    DELETE /api/categories/<id>/  → delete
    """
    def get(self, request, pk):
        CategoryTag.ensure_defaults()
        cat = get_object_or_404(Category.objects.prefetch_related('tags'), pk=pk)
        return success(CategorySerializer(cat, context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        CategoryTag.ensure_defaults()
        cat = get_object_or_404(Category, pk=pk)
        old_image = cat.image
        s = CategorySerializer(cat, data=request.data, partial=True, context={'request': request})
        if s.is_valid():
            updated = s.save()
            if 'is_popular' in request.data and 'tag_ids' not in request.data:
                _sync_legacy_popular_tag(updated)
            _sync_popular_flag(updated)
            if request.FILES.get('image') and old_image and old_image.name != getattr(updated.image, 'name', None):
                old_image.delete(save=False)
            read = CategorySerializer(updated, context={'request': request})
            return success(read.data, 'Category updated')
        return error('Validation failed', s.errors)

    def delete(self, request, pk):
        cat = get_object_or_404(Category, pk=pk)
        if cat.image:
            cat.image.delete(save=False)
        cat.delete()
        return success(msg='Category deleted')


# ══════════════════════════════════════════════════════════════
# PRODUCTS  —  /api/products/
# ══════════════════════════════════════════════════════════════

class ProductListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]

    """
    GET  /api/products/          → list all products (with filters)
    POST /api/products/          → create product + upload images
    """
    def get(self, request):
        qs = Product.objects.select_related('category').prefetch_related('images')

        # ── Filters ──────────────────────────────────────────
        category   = request.query_params.get('category')
        status_f   = request.query_params.get('status')
        search     = request.query_params.get('search')
        min_price  = request.query_params.get('min_price')
        max_price  = request.query_params.get('max_price')
        in_stock   = request.query_params.get('in_stock')

        if category:
            qs = qs.filter(category__slug=category)
        if status_f:
            qs = qs.filter(status=status_f)
        if search:
            qs = qs.filter(name__icontains=search)
        min_price_value, min_price_error = parse_decimal_filter(min_price, 'min_price')
        max_price_value, max_price_error = parse_decimal_filter(max_price, 'max_price')
        if min_price_error or max_price_error:
            return error('Validation failed', {**(min_price_error or {}), **(max_price_error or {})})
        if min_price_value is not None:
            qs = qs.filter(price__gte=min_price_value)
        if max_price_value is not None:
            qs = qs.filter(price__lte=max_price_value)
        if in_stock == 'true':
            qs = qs.filter(stock__gt=0)

        serializer = ProductReadSerializer(qs, many=True, context={'request': request})
        return success({
            'count':    qs.count(),
            'products': serializer.data,
        })

    def post(self, request):
        s = ProductWriteSerializer(data=request.data, context={'request': request})
        if s.is_valid():
            product = s.save()
            read    = ProductReadSerializer(product, context={'request': request})
            return success(read.data, 'Product created', 201)
        return error('Validation failed', s.errors)


class ProductDetailView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]

    """
    GET    /api/products/<id>/   → single product (full nested)
    PUT    /api/products/<id>/   → update product fields + add more images
    DELETE /api/products/<id>/   → delete product + all images
    """
    def get(self, request, pk):
        product = get_object_or_404(
            Product.objects.select_related('category').prefetch_related('images'),
            pk=pk
        )
        return success(ProductReadSerializer(product, context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        s = ProductWriteSerializer(
            product, data=request.data,
            partial=True, context={'request': request}
        )
        if s.is_valid():
            updated = s.save()
            read    = ProductReadSerializer(updated, context={'request': request})
            return success(read.data, 'Product updated')
        return error('Validation failed', s.errors)

    def delete(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        # Delete image files from disk too
        for img in product.images.all():
            if img.image:
                img.image.delete(save=False)
        product.delete()
        return success(msg='Product deleted')


# ══════════════════════════════════════════════════════════════
# PRODUCT IMAGES  —  manage gallery separately
# ══════════════════════════════════════════════════════════════

class ProductImageView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AdminWritePermission]

    """
    POST   /api/products/<id>/images/           → add more images to existing product
    DELETE /api/products/<id>/images/<image_id>/ → delete one image
    PATCH  /api/products/<id>/images/<image_id>/ → set as primary
    """
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        files   = request.FILES.getlist('images')
        if not files:
            return error('No images provided')
        image_field = ProductUploadImageField()
        validated_files = []
        for file in files:
            try:
                validated_files.append(image_field.run_validation(file))
            except Exception as exc:
                detail = getattr(exc, 'detail', str(exc))
                return error('Validation failed', {'images': detail})

        existing = product.images.count()
        created  = []
        for i, f in enumerate(validated_files):
            img = ProductImage.objects.create(
                product=product,
                image=f,
                is_primary=False,
                order=existing + i,
            )
            created.append(ProductImageSerializer(img, context={'request': request}).data)
        return success(created, f'{len(created)} image(s) added', 201)

    def delete(self, request, pk, image_id):
        product = get_object_or_404(Product, pk=pk)
        img     = get_object_or_404(ProductImage, pk=image_id, product=product)
        if product.images.count() == 1:
            return error(
                'Validation failed',
                {'image': 'A product must keep at least one image.'}
            )

        was_primary = img.is_primary
        if img.image:
            img.image.delete(save=False)
        img.delete()

        # If deleted image was primary, promote next one
        if was_primary:
            next_img = product.images.first()
            if next_img:
                next_img.is_primary = True
                next_img.save()

        return success(msg='Image deleted')

    def patch(self, request, pk, image_id):
        product = get_object_or_404(Product, pk=pk)
        img     = get_object_or_404(ProductImage, pk=image_id, product=product)
        img.is_primary = True
        img.save()   # model save() handles unsetting others
        return success(
            ProductImageSerializer(img, context={'request': request}).data,
            'Primary image updated'
        )


# ══════════════════════════════════════════════════════════════
# CAROUSEL  —  /api/carousel/
# ══════════════════════════════════════════════════════════════

class CarouselListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]

    """
    GET  /api/carousel/       → active carousel items for home page
    POST /api/carousel/       → create carousel item (image required)
    """
    def get(self, request):
        qs = CarouselItem.objects.select_related('product').order_by('order', 'id')
        if request.query_params.get('all') == 'true':
            if request.session.get('admin_authenticated') is not True:
                return error('Admin login is required for this operation.', code=403)
        else:
            qs = qs.filter(is_active=True)

        serializer = CarouselItemSerializer(qs, many=True, context={'request': request})
        return success({
            'count': qs.count(),
            'items': serializer.data,
        })

    def post(self, request):
        s = CarouselItemSerializer(data=request.data, context={'request': request})
        if s.is_valid():
            item = s.save()
            read = CarouselItemSerializer(item, context={'request': request})
            return success(read.data, 'Carousel item created', 201)
        return error('Validation failed', s.errors)


class CarouselDetailView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]

    """
    GET    /api/carousel/<id>/  → single carousel item
    PUT    /api/carousel/<id>/  → update carousel item
    PATCH  /api/carousel/<id>/  → partial update
    DELETE /api/carousel/<id>/  → delete carousel item
    """
    def get(self, request, pk):
        item = get_object_or_404(
            CarouselItem.objects.select_related('product'),
            pk=pk,
        )
        return success(CarouselItemSerializer(item, context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        item = get_object_or_404(CarouselItem, pk=pk)
        old_image = item.image
        s = CarouselItemSerializer(
            item, data=request.data, partial=True, context={'request': request},
        )
        if s.is_valid():
            updated = s.save()
            if request.FILES.get('image') and old_image and old_image.name != updated.image.name:
                old_image.delete(save=False)
            read = CarouselItemSerializer(updated, context={'request': request})
            return success(read.data, 'Carousel item updated')
        return error('Validation failed', s.errors)

    def delete(self, request, pk):
        item = get_object_or_404(CarouselItem, pk=pk)
        if item.image:
            item.image.delete(save=False)
        item.delete()
        return success(msg='Carousel item deleted')


class HomeThemeView(APIView):
    permission_classes = [AdminWritePermission]

    def get(self, request):
        theme = HomeTheme.current()
        return success(HomeThemeSerializer(theme).data)

    def patch(self, request):
        theme = HomeTheme.current()
        serializer = HomeThemeSerializer(theme, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success(serializer.data, 'Theme updated')
        return error('Validation failed', serializer.errors)

    def put(self, request):
        theme = HomeTheme.current()
        serializer = HomeThemeSerializer(theme, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success(serializer.data, 'Theme updated')
        return error('Validation failed', serializer.errors)


class HomeSectionListCreateView(APIView):
    permission_classes = [AdminWritePermission]

    def get(self, request):
        HomeSection.ensure_defaults()
        qs = HomeSection.objects.prefetch_related(
            'category_links__category',
            'product_links__product__category',
            'product_links__product__images',
        ).order_by('display_order', 'id')
        if request.query_params.get('all') == 'true':
            if request.session.get('admin_authenticated') is not True:
                return error('Admin login is required for this operation.', code=403)
        else:
            qs = qs.filter(is_visible=True)
        serializer = HomeSectionSerializer(qs, many=True, context={'request': request})
        return success({'count': qs.count(), 'sections': serializer.data})

    def post(self, request):
        serializer = HomeSectionSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            section = serializer.save()
            return success(
                HomeSectionSerializer(section, context={'request': request}).data,
                'Home section created',
                201,
            )
        return error('Validation failed', serializer.errors)


class HomeSectionDetailView(APIView):
    permission_classes = [AdminWritePermission]

    def get(self, request, pk):
        section = get_object_or_404(HomeSection, pk=pk)
        return success(HomeSectionSerializer(section, context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        section = get_object_or_404(HomeSection, pk=pk)
        serializer = HomeSectionSerializer(
            section,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            updated = serializer.save()
            return success(
                HomeSectionSerializer(updated, context={'request': request}).data,
                'Home section updated',
            )
        return error('Validation failed', serializer.errors)

    def delete(self, request, pk):
        section = get_object_or_404(HomeSection, pk=pk)
        section.delete()
        return success(msg='Home section deleted')


def _active_offer_queryset():
    now = timezone.now()
    return Offer.objects.select_related('category', 'product').prefetch_related(
        'product__images',
    ).filter(
        status=Offer.Status.ACTIVE,
    ).filter(
        Q(start_at__isnull=True) | Q(start_at__lte=now),
    ).filter(
        Q(no_expiry=True) | Q(end_at__gte=now),
    )


class OfferListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]

    def get(self, request):
        qs = Offer.objects.select_related('category', 'product').prefetch_related(
            'product__images',
        ).order_by('display_priority_pc', 'id')

        if request.query_params.get('active') in ('true', '1', 'yes'):
            qs = _active_offer_queryset()
        elif request.query_params.get('all') == 'true':
            if request.session.get('admin_authenticated') is not True:
                return error('Admin login is required for this operation.', code=403)
        else:
            qs = _active_offer_queryset()

        placement = request.query_params.get('placement')
        if placement == 'home':
            qs = qs.filter(display_on_home=True, show_as_popup=False)
        elif placement == 'offer_page':
            qs = qs.filter(display_on_offer_page=True, show_as_popup=False)
        elif placement == 'popup':
            qs = qs.filter(show_as_popup=True)

        serializer = OfferSerializer(qs, many=True, context={'request': request})
        return success({'count': qs.count(), 'offers': serializer.data})

    def post(self, request):
        serializer = OfferSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            offer = serializer.save()
            return success(
                OfferSerializer(offer, context={'request': request}).data,
                'Offer created',
                201,
            )
        return error('Validation failed', serializer.errors)


class OfferDetailView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]

    def get(self, request, pk):
        offer = get_object_or_404(
            Offer.objects.select_related('category', 'product').prefetch_related('product__images'),
            pk=pk,
        )
        return success(OfferSerializer(offer, context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        old_banner_image = offer.banner_image
        old_popup_image = offer.popup_image
        serializer = OfferSerializer(
            offer,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if serializer.is_valid():
            updated = serializer.save()
            if request.FILES.get('banner_image') and old_banner_image and old_banner_image.name != updated.banner_image.name:
                old_banner_image.delete(save=False)
            if (
                request.FILES.get('popup_image')
                and old_popup_image
                and old_popup_image.name != getattr(updated.popup_image, 'name', None)
            ):
                old_popup_image.delete(save=False)
            return success(
                OfferSerializer(updated, context={'request': request}).data,
                'Offer updated',
            )
        return error('Validation failed', serializer.errors)

    def delete(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        if offer.banner_image:
            offer.banner_image.delete(save=False)
        if offer.popup_image:
            offer.popup_image.delete(save=False)
        offer.delete()
        return success(msg='Offer deleted')


class ActiveOfferListView(APIView):
    def get(self, request):
        qs = _active_offer_queryset().filter(show_as_popup=False).order_by(
            'display_priority_pc', 'id',
        )
        placement = request.query_params.get('placement')
        if placement == 'home':
            qs = qs.filter(display_on_home=True)
        elif placement == 'offer_page':
            qs = qs.filter(display_on_offer_page=True)
        serializer = OfferSerializer(qs, many=True, context={'request': request})
        return success({'count': qs.count(), 'offers': serializer.data})


class PopupOfferView(APIView):
    def get(self, request):
        offer = _active_offer_queryset().filter(show_as_popup=True).order_by(
            'display_priority_pc', 'id',
        ).first()
        if not offer:
            return success(None, 'No active popup offer')
        return success(OfferSerializer(offer, context={'request': request}).data)


class OfferToggleStatusView(APIView):
    permission_classes = [AdminWritePermission]

    def patch(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        status_value = request.data.get('status')
        if status_value in (Offer.Status.ACTIVE, Offer.Status.INACTIVE):
            offer.status = status_value
        else:
            offer.status = (
                Offer.Status.INACTIVE
                if offer.status == Offer.Status.ACTIVE
                else Offer.Status.ACTIVE
            )
        offer.save(update_fields=['status', 'updated_at'])
        return success(OfferSerializer(offer, context={'request': request}).data, 'Offer status updated')
