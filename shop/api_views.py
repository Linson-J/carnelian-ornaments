from rest_framework.views      import APIView
from rest_framework.response   import Response
from rest_framework            import status
from rest_framework.parsers    import MultiPartParser, FormParser, JSONParser
from django.shortcuts          import get_object_or_404

from .models       import Category, Product, ProductImage
from .serializers  import (
    CategorySerializer,
    ProductReadSerializer,
    ProductWriteSerializer,
    ProductImageSerializer,
)


def success(data=None, msg='Success', code=200):
    return Response({'success': True,  'message': msg,   'data': data},   status=code)

def error(msg='Error', errors=None, code=400):
    return Response({'success': False, 'message': msg, 'errors': errors}, status=code)


# ══════════════════════════════════════════════════════════════
# CATEGORY  —  /api/categories/
# ══════════════════════════════════════════════════════════════

class CategoryListCreateView(APIView):
    """
    GET  /api/categories/       → list all categories
    POST /api/categories/       → create category
    """
    def get(self, request):
        cats = Category.objects.all()
        return success(CategorySerializer(cats, many=True).data)

    def post(self, request):
        s = CategorySerializer(data=request.data)
        if s.is_valid():
            s.save()
            return success(s.data, 'Category created', 201)
        return error('Validation failed', s.errors)


class CategoryDetailView(APIView):
    """
    GET    /api/categories/<id>/  → single category
    PUT    /api/categories/<id>/  → update
    DELETE /api/categories/<id>/  → delete
    """
    def get(self, request, pk):
        cat = get_object_or_404(Category, pk=pk)
        return success(CategorySerializer(cat).data)

    def put(self, request, pk):
        cat = get_object_or_404(Category, pk=pk)
        s   = CategorySerializer(cat, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return success(s.data, 'Category updated')
        return error('Validation failed', s.errors)

    def delete(self, request, pk):
        cat = get_object_or_404(Category, pk=pk)
        cat.delete()
        return success(msg='Category deleted')


# ══════════════════════════════════════════════════════════════
# PRODUCTS  —  /api/products/
# ══════════════════════════════════════════════════════════════

class ProductListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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

        existing = product.images.count()
        created  = []
        for i, f in enumerate(files):
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