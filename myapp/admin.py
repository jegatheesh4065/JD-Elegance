from django.contrib import admin
from .models import *


admin.site.register(Product) 
admin.site.register(Order)
admin.site.register(CartItem)
admin.site.register(ProductVariant)
admin.site.register(CustomerProfile)

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'discount_percentage',
        'minimum_amount',
        'active',
        'valid_from',
        'valid_to'
    )

    search_fields = ('code',)
    list_filter = ('active',)


