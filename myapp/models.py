from django.db import models
from django.conf import settings
from django.utils import timezone

# Create your models here
class Category(models.Model):

    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/')
    stock = models.PositiveIntegerField(default=0)
    offer_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    offer_start_date = models.DateTimeField(
        null=True,
        blank=True
    )

    offer_end_date = models.DateTimeField(
        null=True,
        blank=True
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products"
    )
    def is_offer_active(self):
        now = timezone.now()

        return (
            self.offer_price is not None
            and self.offer_price > 0
            and self.offer_price < self.price
            and self.offer_start_date is not None
            and self.offer_end_date is not None
            and self.offer_start_date <= now <= self.offer_end_date
        )

    def get_display_price(self):
        if self.is_offer_active():
            return self.offer_price

        return self.price

    def discount_percentage(self):
        if self.is_offer_active():
            discount = (
                (self.price - self.offer_price) / self.price
            ) * 100

            return round(discount)

        return 0


    def __str__(self):
        return self.name

class ProductVariant(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants"
    )

    size = models.CharField(max_length=50)

    shade_color = models.CharField(
        max_length=20,
        default="#C76B78"
    )

    shade_image = models.ImageField(
        upload_to="product_shades/",
        null=True,
        blank=True
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    stock = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} - {self.size}"

class CartItem(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def total_price(self):
        return self.product.price * self.quantity
    
class Order(models.Model):

    full_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=10)
    address = models.TextField()
    city = models.CharField(max_length=50)
    pincode = models.CharField(max_length=6)

    payment = models.CharField(max_length=20)
    delivery_status = models.CharField(max_length=30,default="Order Placed")
    expected_delivery = models.DateField(null=True,blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
        null=True,
        blank=True)

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    order_date = models.DateTimeField(auto_now_add=True)
    PAYMENT_STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Paid", "Paid"),
        ("Failed", "Failed"),
        ("Refunded", "Refunded"),
    ]

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="Pending"
    )

    payment_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    payment_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    def __str__(self):
        return self.full_name

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)

    name = models.CharField(max_length=200)
    image = models.ImageField(max_length=500)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def total_price(self):
        return self.price * self.quantity

    def __str__(self):
        return self.name

class CustomerProfile(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customerprofile"
    )

    profile_photo = models.ImageField(
        upload_to="profile_photos/",
        blank=True,
        null=True
    )

    def __str__(self):
        return self.user.username
    
class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percentage = models.PositiveIntegerField(default=10)
    minimum_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField()

    def __str__(self):
        return self.code