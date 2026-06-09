from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from .forms import CarouselItemForm
from .models import CarouselItem, Category, Product, ProductImage


def test_image(name='product.gif'):
    return SimpleUploadedFile(
        name,
        (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,'
            b'\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        ),
        content_type='image/gif',
    )


class ProductAPITests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Accessories', slug='accessories')
        session = self.client.session
        session['admin_authenticated'] = True
        session.save()

    def product_payload(self, **overrides):
        payload = {
            'name': 'Wireless Headphones',
            'description': 'Noise cancelling headphones',
            'price': '100.00',
            'discount_price': '80.00',
            'category': self.category.id,
            'stock': 5,
            'status': Product.Status.AVAILABLE,
            'colors': '["Black", "Blue"]',
            'uploaded_images': [test_image()],
        }
        payload.update(overrides)
        return payload

    def create_product(self):
        response = self.client.post(
            '/api/products/', self.product_payload(), format='multipart'
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Product.objects.get(pk=response.data['data']['id'])

    def test_product_writes_require_admin_session(self):
        self.client.session.flush()

        response = self.client.post(
            '/api/products/', self.product_payload(), format='multipart'
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Product.objects.count(), 0)

    def test_create_validates_discount_price(self):
        response = self.client.post(
            '/api/products/',
            self.product_payload(discount_price='100.00'),
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('discount_price', response.data['errors'])
        self.assertEqual(Product.objects.count(), 0)

    def test_create_update_and_delete_product_through_api(self):
        product = self.create_product()
        self.assertEqual(product.colors, ['Black', 'Blue'])
        self.assertEqual(product.images.count(), 1)

        response = self.client.patch(
            f'/api/products/{product.id}/',
            {
                'name': 'Updated Headphones',
                'price': '120.00',
                'discount_price': '',
                'uploaded_images': [test_image('second.gif')],
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        product.refresh_from_db()
        self.assertEqual(product.name, 'Updated Headphones')
        self.assertIsNone(product.discount_price)
        self.assertEqual(product.images.count(), 2)

        response = self.client.delete(f'/api/products/{product.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(Product.objects.filter(pk=product.id).exists())

    def test_update_cannot_remove_last_product_image(self):
        product = self.create_product()
        image = product.images.get()

        response = self.client.patch(
            f'/api/products/{product.id}/',
            {'removed_image_ids': [image.id]},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('removed_image_ids', response.data['errors'])
        self.assertTrue(ProductImage.objects.filter(pk=image.id).exists())

    def test_admin_product_templates_render(self):
        product = self.create_product()

        list_response = self.client.get('/admin-panel/products/')
        add_response = self.client.get('/admin-panel/products/add/')
        edit_response = self.client.get(f'/admin-panel/products/{product.id}/edit/')

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(edit_response.status_code, 200)


class CarouselManagementTests(APITestCase):
    def setUp(self):
        session = self.client.session
        session['admin_authenticated'] = True
        session.save()
        category = Category.objects.create(name='Fashion', slug='fashion')
        self.product = Product.objects.create(
            name='Linen Dress',
            description='A relaxed linen dress.',
            price='120.00',
            category=category,
            stock=3,
        )

    def carousel_payload(self, **overrides):
        payload = {
            'image': test_image('carousel.gif'),
            'title': 'Summer collection',
            'description': 'Discover the latest collection.',
            'button_text': 'Shop now',
            'redirect_type': CarouselItem.RedirectType.PAGE,
            'customer_page': CarouselItem.CustomerPage.SHOP,
            'order': 1,
            'is_active': True,
        }
        payload.update(overrides)
        return payload

    def test_carousel_form_requires_matching_redirect_destination(self):
        form = CarouselItemForm(data=self.carousel_payload(
            image=None,
            redirect_type=CarouselItem.RedirectType.PRODUCT,
            customer_page=CarouselItem.CustomerPage.HOME,
            product='',
        ), files={'image': test_image('validation.gif')})

        self.assertFalse(form.is_valid())
        self.assertIn('product', form.errors)

    def test_admin_can_create_unlimited_carousel_items_and_home_renders_active_items(self):
        for index in range(4):
            response = self.client.post(
                '/admin-panel/carousel/add/',
                self.carousel_payload(
                    image=test_image(f'carousel-{index}.gif'),
                    title=f'Slide {index}',
                    order=index,
                ),
                format='multipart',
            )
            self.assertEqual(response.status_code, 302)

        self.assertEqual(CarouselItem.objects.count(), 4)
        home = self.client.get('/')
        self.assertContains(home, 'Slide 0')
        self.assertContains(home, 'href="/#collection"')

    def test_product_redirect_points_to_working_product_page(self):
        item = CarouselItem.objects.create(
            image=test_image('product-carousel.gif'),
            title='Featured product',
            description='Our featured product.',
            button_text='View product',
            redirect_type=CarouselItem.RedirectType.PRODUCT,
            product=self.product,
        )

        self.assertEqual(item.redirect_url, f'/products/{self.product.slug}/')
        response = self.client.get(item.redirect_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_carousel_form_accepts_image_only_item(self):
        form = CarouselItemForm(data={}, files={'image': test_image('image-only.gif')})
        self.assertTrue(form.is_valid(), form.errors)

    def test_home_renders_image_only_carousel_without_overlay(self):
        CarouselItem.objects.create(
            image=test_image('image-only-home.gif'),
            is_active=True,
        )
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, 'hero-slide--image-only')

    def test_mobile_image_falls_back_to_desktop_image(self):
        item = CarouselItem.objects.create(
            image=test_image('desktop-only.gif'),
            is_active=True,
        )
        self.assertEqual(item.mobile_display_image, item.image)

        item.mobile_image = test_image('mobile-only.gif')
        item.save()
        self.assertEqual(item.mobile_display_image, item.mobile_image)


class CarouselAPITests(APITestCase):
    def setUp(self):
        session = self.client.session
        session['admin_authenticated'] = True
        session.save()
        category = Category.objects.create(name='Fashion', slug='fashion')
        self.product = Product.objects.create(
            name='Linen Dress',
            description='A relaxed linen dress.',
            price='120.00',
            category=category,
            stock=3,
        )

    def carousel_payload(self, **overrides):
        payload = {
            'image': test_image('api-carousel.gif'),
            'order': 1,
            'is_active': True,
        }
        payload.update(overrides)
        return payload

    def test_public_carousel_list_returns_active_items_only(self):
        CarouselItem.objects.create(
            image=test_image('active.gif'), title='Active slide', is_active=True,
        )
        CarouselItem.objects.create(
            image=test_image('inactive.gif'), title='Hidden slide', is_active=False,
        )

        response = self.client.get('/api/carousel/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['count'], 1)
        self.assertEqual(response.data['data']['items'][0]['title'], 'Active slide')

    def test_create_update_and_delete_carousel_through_api(self):
        create = self.client.post(
            '/api/carousel/', self.carousel_payload(title='Summer'), format='multipart',
        )
        self.assertEqual(create.status_code, 201, create.data)
        item_id = create.data['data']['id']

        image_only = self.client.post(
            '/api/carousel/', self.carousel_payload(image=test_image('plain.gif')), format='multipart',
        )
        self.assertEqual(image_only.status_code, 201, image_only.data)
        self.assertEqual(image_only.data['data']['title'], '')

        update = self.client.patch(
            f'/api/carousel/{item_id}/',
            {'title': 'Updated slide', 'is_active': False},
            format='multipart',
        )
        self.assertEqual(update.status_code, 200, update.data)
        self.assertEqual(update.data['data']['title'], 'Updated slide')

        delete = self.client.delete(f'/api/carousel/{item_id}/')
        self.assertEqual(delete.status_code, 200, delete.data)
        self.assertFalse(CarouselItem.objects.filter(pk=item_id).exists())

    def test_carousel_writes_require_admin_session(self):
        self.client.session.flush()
        response = self.client.post(
            '/api/carousel/', self.carousel_payload(), format='multipart',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CarouselItem.objects.count(), 0)

    def test_create_requires_image(self):
        response = self.client.post('/api/carousel/', {'title': 'No image'}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.data['errors'])

    def test_api_returns_mobile_display_image_url(self):
        create = self.client.post(
            '/api/carousel/',
            self.carousel_payload(title='Desktop only'),
            format='multipart',
        )
        self.assertEqual(create.status_code, 201, create.data)
        data = create.data['data']
        self.assertEqual(data['mobile_image_url'], None)
        self.assertEqual(data['mobile_display_image_url'], data['image_url'])

        with_mobile = self.client.post(
            '/api/carousel/',
            self.carousel_payload(
                image=test_image('desktop-2.gif'),
                mobile_image=test_image('mobile-2.gif'),
                title='Both images',
            ),
            format='multipart',
        )
        self.assertEqual(with_mobile.status_code, 201, with_mobile.data)
        mobile_data = with_mobile.data['data']
        self.assertIsNotNone(mobile_data['mobile_image_url'])
        self.assertEqual(
            mobile_data['mobile_display_image_url'],
            mobile_data['mobile_image_url'],
        )
