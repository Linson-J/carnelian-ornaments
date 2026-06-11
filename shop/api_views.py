from rest_framework.views      import APIView
from rest_framework.response   import Response
from rest_framework            import status
from rest_framework.parsers    import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.shortcuts          import get_object_or_404

from .models       import Category, Product, ProductImage, CarouselItem, HomeTheme
from .serializers  import (
    CategorySerializer,
    ProductReadSerializer,
    ProductWriteSerializer,
    ProductImageSerializer,
    ProductUploadImageField,
    CarouselItemSerializer,
    HomeThemeSerializer,
)


def success(data=None, msg='Success', code=200):
    return Response({'success': True,  'message': msg,   'data': data},   status=code)

def error(msg='Error', errors=None, code=400):
    return Response({'success': False, 'message': msg, 'errors': errors}, status=code)


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

class CategoryListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [AdminWritePermission]
    """
    GET  /api/categories/       → list all categories
    POST /api/categories/       → create category
    """
    def get(self, request):
        cats = Category.objects.all()
        status_f = request.query_params.get('status')
        if status_f:
            cats = cats.filter(status=status_f)
        popular_f = request.query_params.get('popular')
        if popular_f in ('true', '1', 'yes'):
            cats = cats.filter(is_popular=True)
        elif popular_f in ('false', '0', 'no'):
            cats = cats.filter(is_popular=False)
        return success(CategorySerializer(cats, many=True, context={'request': request}).data)

    def post(self, request):
        s = CategorySerializer(data=request.data, context={'request': request})
        if s.is_valid():
            s.save()
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
        cat = get_object_or_404(Category, pk=pk)
        return success(CategorySerializer(cat, context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk)

    def patch(self, request, pk):
        return self._update(request, pk)

    def _update(self, request, pk):
        cat = get_object_or_404(Category, pk=pk)
        old_image = cat.image
        s = CategorySerializer(cat, data=request.data, partial=True, context={'request': request})
        if s.is_valid():
            updated = s.save()
            if request.FILES.get('image') and old_image and old_image.name != getattr(updated.image, 'name', None):
                old_image.delete(save=False)
            return success(s.data, 'Category updated')
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
        if min_price:
            qs = qs.filter(price__gte=min_price)
        if max_price:
            qs = qs.filter(price__lte=max_price)
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
        old_mobile_image = item.mobile_image
        s = CarouselItemSerializer(
            item, data=request.data, partial=True, context={'request': request},
        )
        if s.is_valid():
            updated = s.save()
            if request.FILES.get('image') and old_image and old_image.name != updated.image.name:
                old_image.delete(save=False)
            if (
                request.FILES.get('mobile_image')
                and old_mobile_image
                and old_mobile_image.name != getattr(updated.mobile_image, 'name', None)
            ):
                old_mobile_image.delete(save=False)
            read = CarouselItemSerializer(updated, context={'request': request})
            return success(read.data, 'Carousel item updated')
        return error('Validation failed', s.errors)

    def delete(self, request, pk):
        item = get_object_or_404(CarouselItem, pk=pk)
        if item.image:
            item.image.delete(save=False)
        if item.mobile_image:
            item.mobile_image.delete(save=False)
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
