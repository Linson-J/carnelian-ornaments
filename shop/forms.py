from django import forms

from .models import CarouselItem, NewsletterSubscription, Product


MAX_CAROUSEL_IMAGE_SIZE = 8 * 1024 * 1024


class NewsletterSubscriptionForm(forms.ModelForm):
    class Meta:
        model = NewsletterSubscription
        fields = ['email']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if NewsletterSubscription.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This email is already subscribed.')
        return email


class CarouselItemForm(forms.ModelForm):
    class Meta:
        model = CarouselItem
        fields = [
            'image', 'mobile_image', 'title', 'description', 'button_text', 'redirect_type',
            'customer_page', 'product', 'order', 'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'image': forms.FileInput(attrs={'accept': 'image/*'}),
            'mobile_image': forms.FileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = (
            'mobile_image', 'title', 'description', 'button_text', 'redirect_type',
            'customer_page', 'product',
        )
        for name in optional_fields:
            self.fields[name].required = False
        self.fields['image'].label = 'Desktop image (PC view)'
        self.fields['mobile_image'].label = 'Mobile image'
        self.fields['redirect_type'].choices = [
            ('', 'No redirect'),
            *CarouselItem.RedirectType.choices,
        ]
        self.fields['product'].queryset = Product.objects.order_by('name')
        self.fields['product'].empty_label = 'Select a product'
        self.fields['customer_page'].choices = [
            ('', 'Select a customer page'),
            *CarouselItem.CustomerPage.choices,
        ]
        self.fields['order'].required = False
        self.fields['order'].help_text = 'Lower numbers appear first.'

    def clean_image(self):
        return self._clean_carousel_image('image')

    def clean_mobile_image(self):
        return self._clean_carousel_image('mobile_image')

    def _clean_carousel_image(self, field_name):
        image = self.cleaned_data.get(field_name)
        if image and image.size > MAX_CAROUSEL_IMAGE_SIZE:
            raise forms.ValidationError('Image must be 8MB or smaller.')
        return image

    def clean(self):
        cleaned_data = super().clean()
        redirect_type = cleaned_data.get('redirect_type')
        customer_page = cleaned_data.get('customer_page')
        product = cleaned_data.get('product')

        if not redirect_type:
            cleaned_data['customer_page'] = ''
            cleaned_data['product'] = None
            return cleaned_data

        if redirect_type == CarouselItem.RedirectType.PAGE:
            if not customer_page:
                self.add_error('customer_page', 'Select a customer page.')
            cleaned_data['product'] = None
        elif redirect_type == CarouselItem.RedirectType.PRODUCT:
            if not product:
                self.add_error('product', 'Select a product.')
            cleaned_data['customer_page'] = ''

        return cleaned_data
