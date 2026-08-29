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


from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from .models import Order, OrderItem

class OrderCancellationAndReturnTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser@example.com', email='testuser@example.com', password='password123')
        self.client.force_login(self.user)
        
        self.category = Category.objects.create(name='Electronics', slug='electronics')
        self.product = Product.objects.create(
            name='Smartphone',
            price=500.00,
            stock=10,
            status=Product.Status.AVAILABLE,
            category=self.category
        )
        
        self.order = Order.objects.create(
            user=self.user,
            full_name='Test User',
            phone='1234567890',
            country='India',
            state='Tamil Nadu',
            city='Chennai',
            street_address='123 Main St',
            postal_code='600001',
            subtotal=500.00,
            delivery_fee=20.00,
            total=520.00,
            status=Order.Status.PROCESSING,
            payment_method='Card'
        )
        
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            price=500.00,
            quantity=1
        )
        self.product.stock = 9  # simulated stock deduction upon order
        self.product.save()

    def test_cancel_order_success_before_shipped(self):
        response = self.client.post(
            f'/order/{self.order.id}/cancel/',
            {'reason': 'Ordered by mistake'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('refund of ₹520.00 will be processed within 2 to 5 working days', data['message'])

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.cancellation_reason, 'Ordered by mistake')
        self.assertTrue(self.order.cancel_requested)

        # Verify stock was restored
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_cancel_order_single_use_restriction(self):
        # First cancellation attempt
        self.client.post(f'/order/{self.order.id}/cancel/', {'reason': 'Reason 1'}, format='json')

        # Second cancellation attempt
        response = self.client.post(f'/order/{self.order.id}/cancel/', {'reason': 'Reason 2'}, format='json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertTrue(data['already_attempted'])
        self.assertIn('Contact customer care!', data['message'])

    def test_cannot_cancel_shipped_order(self):
        self.order.status = Order.Status.SHIPPED
        self.order.save()

        response = self.client.post(f'/order/{self.order.id}/cancel/', {'reason': 'Late delivery'}, format='json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Order cannot be cancelled as it has already been shipped', data['message'])

    def test_return_order_success_within_7_days(self):
        self.order.status = Order.Status.DELIVERED
        self.order.delivered_at = timezone.now() - timedelta(days=2)
        self.order.save()

        response = self.client.post(
            f'/order/{self.order.id}/return/',
            {'reason': 'Defective item'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('refund/replacement will be processed within 2 to 5 working days', data['message'])

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.RETURN_REQUESTED)
        self.assertEqual(self.order.return_reason, 'Defective item')
        self.assertTrue(self.order.return_requested)

    def test_cannot_return_order_after_7_days(self):
        self.order.status = Order.Status.DELIVERED
        self.order.delivered_at = timezone.now() - timedelta(days=8)
        self.order.save()

        response = self.client.post(f'/order/{self.order.id}/return/', {'reason': 'Item no longer needed'}, format='json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('7-day replacement window for this order has expired', data['message'])

    def test_return_order_single_use_restriction(self):
        self.order.status = Order.Status.DELIVERED
        self.order.delivered_at = timezone.now() - timedelta(days=1)
        self.order.save()

        # First return attempt
        self.client.post(f'/order/{self.order.id}/return/', {'reason': 'Damaged product'}, format='json')

        # Second return attempt
        response = self.client.post(f'/order/{self.order.id}/return/', {'reason': 'Try again'}, format='json')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertTrue(data['already_attempted'])
        self.assertIn('Contact customer care!', data['message'])

    def test_admin_orders_view_displays_cancellation_and_return_reasons(self):
        session = self.client.session
        session['admin_authenticated'] = True
        session.save()

        self.order.status = Order.Status.CANCELLED
        self.order.cancellation_reason = 'Wrong address entered'
        self.order.cancelled_at = timezone.now()
        self.order.cancel_requested = True
        self.order.save()

        admin_resp = self.client.get('/admin-panel/orders/')
        self.assertEqual(admin_resp.status_code, 200)
        self.assertContains(admin_resp, 'Order Cancelled by Customer')
        self.assertContains(admin_resp, 'Wrong address entered')
        self.assertContains(admin_resp, 'Refund of ₹520.00 to be credited within 2 to 5 working days')
        self.assertContains(admin_resp, 'Cancelled (Locked)')

    def test_admin_can_change_status_of_returned_order(self):
        session = self.client.session
        session['admin_authenticated'] = True
        session.save()

        # Test cancelled lock
        self.order.status = Order.Status.CANCELLED
        self.order.save()
        resp_cancel = self.client.post(
            f'/admin-panel/orders/{self.order.id}/status/',
            {'status': 'delivered'},
            follow=True
        )
        self.assertEqual(resp_cancel.status_code, 200)
        self.assertContains(resp_cancel, 'already cancelled and cannot be changed')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)

        # Test return/replacement is NOT locked
        self.order.status = Order.Status.RETURN_REQUESTED
        self.order.save()
        resp_return = self.client.post(
            f'/admin-panel/orders/{self.order.id}/status/',
            {'status': 'returned'},
            follow=True
        )
        self.assertEqual(resp_return.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.RETURNED)



