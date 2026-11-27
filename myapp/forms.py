from django import forms
from .models import *

class CheckoutForm(forms.Form):

    full_name = forms.CharField(
        max_length=50,
        required=True,
        error_messages={
            "required": "Please enter your full name."
        }
    )

    phone = forms.CharField(
        max_length=10,
        min_length=10,
        required=True,
        error_messages={
            "required": "Please enter your phone number.",
            "min_length": "Phone number must contain 10 digits.",
            "max_length": "Phone number must contain 10 digits."
        }
    )

    address = forms.CharField(
        max_length=200,
        required=True,
        error_messages={
            "required": "Please enter your delivery address."
        }
    )

    city = forms.CharField(
        max_length=50,
        required=True,
        error_messages={
            "required": "Please enter your city."
        }
    )

    pincode = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        error_messages={
            "required": "Please enter your pincode.",
            "min_length": "Pincode must contain 6 digits.",
            "max_length": "Pincode must contain 6 digits."
        }
    )

    payment = forms.ChoiceField(
        choices=[
            ("cod", "Cash on Delivery"),
            ("upi", "UPI"),
            ("card", "Credit / Debit Card"),
            ("netbanking", "Net Banking"),
        ],
        required=True,
        error_messages={
            "required": "Please select a payment method."
        }
    )

    def clean_full_name(self):

        name = self.cleaned_data["full_name"]

        if not name.replace(" ", "").isalpha():
            raise forms.ValidationError(
                "Name should contain only letters."
            )

        return name

    def clean_phone(self):

        phone = self.cleaned_data["phone"]

        if not phone.isdigit():
            raise forms.ValidationError(
                "Phone number should contain only digits."
            )

        if len(phone) != 10:
            raise forms.ValidationError(
                "Phone number must contain 10 digits."
            )

        return phone

    def clean_city(self):

        city = self.cleaned_data["city"]

        if not city.replace(" ", "").isalpha():
            raise forms.ValidationError(
                "City should contain only letters."
            )

        return city

    def clean_pincode(self):

        pincode = self.cleaned_data["pincode"]

        if not pincode.isdigit():
            raise forms.ValidationError(
                "Pincode should contain only digits."
            )

        if len(pincode) != 6:
            raise forms.ValidationError(
                "Pincode must contain 6 digits."
            )

        return pincode

class CategoryForm(forms.ModelForm):

    class Meta:
        model = Category
        fields = ["name"]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter category name"
                }
            )
        }

class ProductForm(forms.ModelForm):

    class Meta:

        model = Product

        fields = [
            "name",
            "price",
            "image",
            "stock",
            "category"
        ]

        widgets = {

            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter product name"
                }
            ),

            "price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter price",
                    "step": "0.01"
                }
            ),

            "stock": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter stock"
                }
            ),

            "category": forms.Select(
                attrs={
                    "class": "form-control"
                }
            ),

        }

class ProductVariantForm(forms.ModelForm):

    class Meta:
        model = ProductVariant

        fields = [
            'size',
            'shade_color',
            'shade_image',
            'price',
            'stock'
        ]

        widgets = {
            'size': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter size or shade name',
                'required': True,
            }),

            'shade_color': forms.TextInput(attrs={
                'class': 'form-input',
                'type': 'color',
            }),

            'shade_image': forms.ClearableFileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*',
            }),

            'price': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter price (e.g. 299)',
                'min': '0.01',
                'step': '0.01',
                'required': True,
            }),

            'stock': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter available stock',
                'min': '0',
                'required': True,
            }),
        }

class CouponForm(forms.ModelForm):

    class Meta:
        model = Coupon
        fields = [
            'code',
            'discount_percentage',
            'minimum_amount',
            'active',
            'valid_from',
            'valid_to'
        ]

        widgets = {
            'valid_from': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}
            ),
            'valid_to': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}
            ),
        }

    def clean_discount_percentage(self):
        discount = self.cleaned_data['discount_percentage']

        if discount < 1 or discount > 100:
            raise forms.ValidationError(
                "Discount must be between 1 and 100."
            )

        return discount

    def clean(self):
        cleaned_data = super().clean()

        valid_from = cleaned_data.get('valid_from')
        valid_to = cleaned_data.get('valid_to')

        if valid_from and valid_to and valid_to <= valid_from:
            raise forms.ValidationError(
                "Expiry date must be after the start date."
            )

        return cleaned_data
