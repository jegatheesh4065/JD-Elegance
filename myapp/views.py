from django.shortcuts import render,redirect,get_object_or_404
from .models import *
from .forms import *
import json
from django.http import JsonResponse
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Q,Sum
from django.utils.dateparse import parse_datetime
from django.db.models import F
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required , user_passes_test
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
import razorpay
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse, request
from django.conf import settings
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models.functions import TruncMonth

def home(request):
    selected_category = request.GET.get('category')
    available_coupons = Coupon.objects.filter(
        active=True,
        valid_from__lte=timezone.now(),
        valid_to__gte=timezone.now()
    ).order_by('-discount_percentage')

    if selected_category and selected_category.isdecimal():
        products = Product.objects.filter(
            category_id=selected_category
        )
    else:
        category_name = selected_category or "selected_category"
        products = Product.objects.filter(
            category__name__iexact=category_name
        )

    return render(request, 'home.html', {
        'products': products,
        'selected_category': selected_category,
        'available_coupons': available_coupons,
    })

@staff_member_required(login_url="/admin-login/")

def add_product(request):

    categories = Category.objects.all()

    if request.method == 'POST':

        name = request.POST.get('name')
        price = request.POST.get('price')
        image = request.FILES.get('image')
        stock = request.POST.get('stock')
        category_id = request.POST.get('category')

        offer_price = request.POST.get('offer_price')
        offer_start_date = request.POST.get('offer_start_date')
        offer_end_date = request.POST.get('offer_end_date')

        # Get category
        category = Category.objects.get(id=category_id)

        start_date = None
        end_date = None

        # Validate offer
        if offer_price:

            if float(offer_price) <= 0 or float(offer_price) >= float(price):

                messages.error(
                    request,
                    'Offer price must be less than the original price.'
                )

                return render(request, 'add_product.html', {
                    'categories': categories
                })

            if not offer_start_date or not offer_end_date:

                messages.error(
                    request,
                    'Please enter offer start date and end date.'
                )

                return render(request, 'add_product.html', {
                    'categories': categories
                })

            start_date = parse_datetime(offer_start_date)
            end_date = parse_datetime(offer_end_date)

            if not start_date or not end_date or end_date <= start_date:

                messages.error(
                    request,
                    'Please enter valid offer dates.'
                )

                return render(request, 'add_product.html', {
                    'categories': categories
                })

            if timezone.is_naive(start_date):
                start_date = timezone.make_aware(start_date)

            if timezone.is_naive(end_date):
                end_date = timezone.make_aware(end_date)

        # Save product
        Product.objects.create(
            name=name,
            price=price,
            image=image,
            stock=stock,
            category=category,
            offer_price=offer_price if offer_price else None,
            offer_start_date=start_date,
            offer_end_date=end_date
        )

        messages.success(request, 'Product added successfully!')

        return redirect('home')

    # IMPORTANT: GET request must return the HTML page
    return render(request, 'add_product.html', {
        'categories': categories
    })
def purchase_product(request, product_id):

    if request.method == "POST":

        product = get_object_or_404(Product, id=product_id)

        if product.stock > 0:

            product.stock -= 1
            product.save()

        return redirect('home')
    
@login_required(login_url='/login/')
def checkout(request):

    form = CheckoutForm(request.POST or None)

    product_id = request.session.get("order_product_id")
    variant_id = request.session.get("order_variant_id")

    try:
        direct_quantity = max(
            1,
            int(request.session.get("order_product_quantity", 1))
        )
    except (ValueError, TypeError):
        direct_quantity = 1

    product = None
    variant = None

    # GET DIRECT BUY NOW PRODUCT
    if product_id:

        product = get_object_or_404(Product, id=product_id)

        if variant_id:
            variant = get_object_or_404(
                ProductVariant,
                id=variant_id,
                product=product
            )

    # READ CART DATA
    cart_data = request.POST.get(
        "cart_data", "[]"
    ) if request.method == "POST" else "[]"

    try:
        cart = json.loads(cart_data)

        if not isinstance(cart, list):
            cart = []

    except (ValueError, TypeError):
        cart = []

    cart_items = []
    cart_total = Decimal("0.00")

    for item in cart:

        if not isinstance(item, dict):
            continue

        product_name = str(item.get("name", "")).strip()

        try:
            item_quantity = int(item.get("quantity", 1))
        except (ValueError, TypeError):
            continue

        if not product_name or item_quantity < 1:
            continue

        # Avoid duplicate direct product
        if product and product.name.casefold() == product_name.casefold():
            continue

        cart_product = Product.objects.filter(
            name__iexact=product_name
        ).first()

        if not cart_product:
            continue

        cart_items.append({
            "product": cart_product,
            "quantity": item_quantity,
            "price": cart_product.price,
        })

        cart_total += cart_product.price * item_quantity

    # CALCULATE TOTAL
    total = cart_total

    if product:

        if variant:
            total += variant.price * direct_quantity

        else:
            total += product.price * direct_quantity

    # COMMON CONTEXT
    context = {
        "form": form,
        "selected_product": product,
        "selected_variant": variant,
        "quantity": direct_quantity,
        "total": total,
        "cart_items": cart_items,
    }

    # APPLY COUPON
    if request.method == "POST" and "apply_coupon" in request.POST:

        coupon_code = request.POST.get(
            "coupon_code", ""
        ).strip()

        request.session.pop("applied_coupon", None)

        coupon_discount = Decimal("0.00")
        applied_coupon = None

        try:
            coupon = Coupon.objects.get(
                code__iexact=coupon_code,
                active=True
            )

            now = timezone.now()

            if not coupon_code:
                messages.error(request, "Please enter a coupon code.")

            elif not (coupon.valid_from <= now <= coupon.valid_to):
                messages.error(request, "This coupon is expired or not yet valid.")

            elif total < coupon.minimum_amount:
                messages.error(
                    request,
                    f"Minimum purchase amount is ₹{coupon.minimum_amount}."
                )

            else:

                coupon_discount = (
                    total * Decimal(coupon.discount_percentage) /
                    Decimal("100")
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )

                applied_coupon = coupon
                request.session["applied_coupon"] = coupon.code

                messages.success(
                    request,
                    f"Coupon {coupon.code} applied successfully!"
                )

        except Coupon.DoesNotExist:
            messages.error(request, "Invalid coupon code.")

        context.update({
            "coupon_discount": coupon_discount,
            "applied_coupon": applied_coupon,
            "coupon_code": coupon_code,
        })

        return render(request, "checkout.html", context)

    # PLACE ORDER
    if request.method == "POST" and form.is_valid():

        with transaction.atomic():

            # VALIDATE DIRECT PRODUCT STOCK
            if product:

                if variant:

                    variant = ProductVariant.objects.select_for_update().get(
                        id=variant.id,
                        product=product
                    )

                    if variant.stock < direct_quantity:

                        context["stock_error"] = (
                            f"Only {variant.stock} item(s) available "
                            f"for {product.name}."
                        )

                        return render(request, "checkout.html", context)

                else:

                    product = Product.objects.select_for_update().get(
                        id=product.id
                    )

                    if product.stock < direct_quantity:

                        context["stock_error"] = (
                            f"Only {product.stock} item(s) available "
                            f"for {product.name}."
                        )

                        return render(request, "checkout.html", context)

            # VALIDATE CART STOCK
            for cart_item in cart_items:

                cart_product = Product.objects.select_for_update().get(
                    id=cart_item["product"].id
                )

                cart_item["product"] = cart_product

                if cart_product.stock < cart_item["quantity"]:

                    context["stock_error"] = (
                        f"Only {cart_product.stock} item(s) available "
                        f"for {cart_product.name}."
                    )

                    return render(request, "checkout.html", context)

            if total <= Decimal("0.00"):

                context["stock_error"] = "Your cart is empty."

                return render(request, "checkout.html", context)

            # REVALIDATE COUPON
            coupon_discount = Decimal("0.00")

            coupon_code = request.session.get("applied_coupon")

            if coupon_code:

                try:
                    coupon = Coupon.objects.get(
                        code__iexact=coupon_code,
                        active=True
                    )

                    now = timezone.now()

                    if (
                        coupon.valid_from <= now <= coupon.valid_to
                        and total >= coupon.minimum_amount
                    ):

                        coupon_discount = (
                            total * Decimal(coupon.discount_percentage) /
                            Decimal("100")
                        ).quantize(
                            Decimal("0.01"),
                            rounding=ROUND_HALF_UP
                        )

                except Coupon.DoesNotExist:
                    pass

            final_total = total - coupon_discount

                       # CREATE ORDER
            payment_method = form.cleaned_data["payment"].lower()

            order = Order.objects.create(
                user=request.user,
                full_name=form.cleaned_data["full_name"],
                phone=form.cleaned_data["phone"],
                address=form.cleaned_data["address"],
                city=form.cleaned_data["city"],
                pincode=form.cleaned_data["pincode"],
                payment=payment_method,
                total_amount=final_total,
                payment_status="Pending"
            )

            # SAVE DIRECT BUY NOW PRODUCT
            if product:

                order_name = (
                    f"{product.name} - {variant.size}"
                    if variant else product.name
                )

                order_price = variant.price if variant else product.price

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    variant=variant,
                    name=order_name,
                    image=product.image.name if product.image else "",
                    price=order_price,
                    quantity=direct_quantity
                )

                # Reduce stock immediately only for COD
                if payment_method == "cod":

                    if variant:
                        variant.stock -= direct_quantity
                        variant.save(update_fields=["stock"])
                    else:
                        product.stock -= direct_quantity
                        product.save(update_fields=["stock"])

            # SAVE CART PRODUCTS
            for cart_item in cart_items:

                cart_product = cart_item["product"]
                item_quantity = cart_item["quantity"]

                OrderItem.objects.create(
                    order=order,
                    product=cart_product,
                    name=cart_product.name,
                    image=(
                        cart_product.image.name
                        if cart_product.image else ""
                    ),
                    price=cart_product.price,
                    quantity=item_quantity
                )

                # Reduce stock immediately only for COD
                if payment_method == "cod":

                    cart_product.stock -= item_quantity
                    cart_product.save(update_fields=["stock"])

            # COD ORDER
            if payment_method == "cod":

                order.payment_status = "Pending"
                order.save(update_fields=["payment_status"])

            # ONLINE PAYMENT
            elif payment_method in ["upi", "netbanking", "card"]:

                client = razorpay.Client(
                    auth=(
                        settings.RAZORPAY_KEY_ID,
                        settings.RAZORPAY_KEY_SECRET
                    )
                )

                razorpay_order = client.order.create({
                    "amount": int(final_total * 100),
                    "currency": "INR",
                    "receipt": f"order_{order.id}"
                })

                order.payment_order_id = razorpay_order["id"]
                order.save(update_fields=["payment_order_id"])

        # ONLINE PAYMENT RESPONSE
        if payment_method in ["upi", "netbanking", "card"]:

            context.update({
                "razorpay_key": settings.RAZORPAY_KEY_ID,
                "razorpay_order_id": order.payment_order_id,
                "razorpay_amount": int(final_total * 100),
                "local_order_id": order.id,
            })

            return render(request, "checkout.html", context)

        # CLEAR SESSION FOR COD
        request.session.pop("order_product_id", None)
        request.session.pop("order_variant_id", None)
        request.session.pop("order_product_quantity", None)
        request.session.pop("applied_coupon", None)

        return redirect("delivery_tracking", order_id=order.id)

    # NORMAL CHECKOUT DISPLAY
    context.update({
        "coupon_discount": Decimal("0.00"),
        "applied_coupon": None,
    })

    return render(request, "checkout.html", context)

def order_details(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id
    )

    items = order.items.all()

    return render(
        request,
        "order_details.html",
        {
            "order": order,
            "items": items
        }
    )
def order_success(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id
    )

    return render(
        request,
        "order_success.html",
        {
            "order": order
        }
    )
@staff_member_required(login_url="/admin-login/")
def dashboard(request):
    products = Product.objects.all()

    today = timezone.localdate()

    # Total products
    total_products = Product.objects.count()

    # Total orders
    total_orders = Order.objects.count()

    # Today's orders
    today_orders = Order.objects.filter(
        order_date__date=today
    ).count()

    # Today's revenue
    today_revenue = Order.objects.filter(
        order_date__date=today
    ).aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    # Total revenue
    total_revenue = Order.objects.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    all_products = Product.objects.all().order_by('name')

    # Recent orders
    recent_orders = Order.objects.order_by(
        "-order_date"
    )[:10]

    # Revenue per day
    daily_revenue = (
        Order.objects
        .annotate(day=TruncDate("order_date"))
        .values("day")
        .annotate(
            revenue=Sum("total_amount"),
            orders=Count("id")
        )
        .order_by("day")
    )

    context = {
        "total_products": total_products,
        "total_orders": total_orders,
        "today_orders": today_orders,
        "today_revenue": today_revenue,
        "total_revenue": total_revenue,
        "all_products": all_products,
        "recent_orders": recent_orders,
        "daily_revenue": daily_revenue,
        'products': products,
    }

    return render(request,"dashboard.html",context)
def admin_login(request):

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None and user.is_staff:

            login(request, user)

            return redirect("dashboard")

        else:

            return render(
                request,
                "admin_login.html",
                {
                    "error": "Invalid admin username or password."
                }
            )

    return render(request, "admin_login.html")
def admin_check(user):
    return user.is_authenticated and user.is_staff


@login_required
@user_passes_test(admin_check, login_url='home')
def admin_profile(request):

    admin_user = request.user

    if request.method == "POST":

        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()

        if not first_name or not last_name or not email:
            messages.error(request, "Please fill in all fields.")

        elif User.objects.filter(email__iexact=email).exclude(
            pk=admin_user.pk
        ).exists():
            messages.error(request, "This email is already in use.")

        else:
            admin_user.first_name = first_name
            admin_user.last_name = last_name
            admin_user.email = email

            admin_user.save()

            messages.success(
                request,
                "Your profile has been updated successfully!"
            )

            return redirect('admin_profile')

    return render(request, 'admin_profile.html', {
        'admin_user': admin_user
    })


@login_required
@user_passes_test(admin_check, login_url='home')
def admin_change_password(request):

    if request.method == "POST":
        form = PasswordChangeForm(
            user=request.user,
            data=request.POST
        )

        if form.is_valid():
            user = form.save()

            update_session_auth_hash(request, user)

            messages.success(
                request,
                "Your password has been changed successfully!"
            )

            return redirect('admin_change_password')

        else:
            messages.error(
                request,
                "Please correct the errors below."
            )

    else:
        form = PasswordChangeForm(user=request.user)

    return render(request, 'admin_change_password.html', {
        'form': form
    })

def admin_logout(request):
    logout(request)
    return redirect("admin_login")
@staff_member_required(login_url="/admin-login/")
def categories(request):

    category_list = Category.objects.all().order_by("name")
    total_products = Product.objects.count()
    return render(
        request,
        "categories.html",
        {
            "categories": category_list,
            "total_products": total_products,
        }
    )


@staff_member_required(login_url="/admin-login/")
def add_category(request):

    if request.method == "POST":

        form = CategoryForm(request.POST)

        if form.is_valid():

            form.save()

            return redirect("categories")

    else:

        form = CategoryForm()

    return render(
        request,
        "add_category.html",
        {
            "form": form
        }
    )
def category_products(request, category_id):
    category = get_object_or_404(Category, id=category_id)

    products = Product.objects.filter(category=category)

    return render(request, "category_products.html", {
        "category": category,
        "products": products
    })
def product_order(request, product_id):

    product = get_object_or_404(Product, id=product_id)

    variants = list(
        ProductVariant.objects.filter(product=product)
    )

    # Check whether product actually has shades
    default_color = "#c76b78"

    has_shades = any(
        variant.shade_image or
        (
            variant.shade_color and
            variant.shade_color.strip().lower() != default_color
        )
        for variant in variants
    )

    def show_order_page(error=None):

        context = {
            "product": product,
            "variants": variants,
            "has_shades": has_shades,
        }

        if error:
            context["stock_error"] = error

        return render(request, "product_order.html", context)

    if request.method == "POST":

        try:
            quantity = int(request.POST.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1

        quantity = max(1, quantity)

        # PRODUCT WITH VARIANTS
        if variants:

            variant_id = request.POST.get("variant_id")

            if not variant_id:
                return show_order_page("Please select an option.")

            variant = get_object_or_404(
                ProductVariant,
                id=variant_id,
                product=product
            )

            if variant.stock < quantity:
                return show_order_page(
                    "Selected option has insufficient stock."
                )

            request.session["order_variant_id"] = variant.id

        # PRODUCT WITHOUT VARIANTS
        else:

            if product.stock < quantity:
                return show_order_page(
                    "This product is currently unavailable."
                )

            request.session.pop("order_variant_id", None)

        request.session["order_product_id"] = product.id

        request.session["order_product_quantity"] = quantity

        return redirect("checkout")

    return show_order_page()
@staff_member_required(login_url="/admin-login/")
def edit_category(request, category_id):

    category = get_object_or_404(
        Category,
        id=category_id
    )

    if request.method == "POST":

        form = CategoryForm(
            request.POST,
            instance=category
        )

        if form.is_valid():

            form.save()

            return redirect("categories")

    else:

        form = CategoryForm(
            instance=category
        )

    return render(
        request,
        "add_category.html",
        {
            "form": form,
            "edit_mode": True
        }
    )


@staff_member_required(login_url="/admin-login/")
def delete_category(request, category_id):

    category = get_object_or_404(
        Category,
        id=category_id
    )

    if request.method == "POST":

        category.delete()

    return redirect("categories")
def send_html_email(request):

    subject = "Welcome to JD Beauty"

    from_email = settings.EMAIL_HOST_USER

    to_email = "receiver@gmail.com"

    context = {
        'username': 'Jegatheesh'
    }

    # Load HTML template
    html_content = render_to_string(
        'email_template.html',
        context
    )

    # Create email
    email = EmailMultiAlternatives(
        subject,
        'Welcome to JD Beauty!',
        from_email,
        [to_email]
    )

    # Attach HTML content
    email.attach_alternative(html_content, "text/html")

    # Send email
    email.send()

    return HttpResponse("HTML Email Sent Successfully!")

def forgot_password(request):

    if request.method == "POST":

        email = request.POST.get("email")

        user = User.objects.filter(email=email).first()

        if user:
            send_html_email(request, user)

        return redirect("password_reset_done")

    return render(request, "password_reset.html")
# @login_required
# @user_passes_test(lambda user: user.is_staff)
# @require_POST
# def restock_product(request, product_id):

#     product = get_object_or_404(Product, id=product_id)

#     try:
#         quantity = int(request.POST.get("quantity", 0))

#         if quantity <= 0:
#             messages.error(request, "Enter a quantity greater than zero.")

#         else:
#             product.stock += quantity
#             product.save(update_fields=["stock"])

#             messages.success(
#                 request,
#                 f"{product.name} restocked successfully! "
#                 f"Current stock: {product.stock}"
#             )

#     except (ValueError, TypeError):
#         messages.error(request, "Please enter a valid quantity.")

#     return redirect("dashboard")
@login_required
def restock_page(request):
    products = Product.objects.all().order_by("name")

    return render(request, "restock_product.html", {
        "products": products
    })


@login_required
@require_POST
def restock_product(request):
    product_id = request.POST.get("product_id")
    quantity = request.POST.get("quantity")

    product = get_object_or_404(Product, id=product_id)

    try:
        quantity = int(quantity)

        if quantity <= 0:
            messages.error(request, "Quantity must be greater than zero.")

        else:
            product.stock += quantity
            product.save(update_fields=["stock"])

            messages.success(
                request,
                f"{product.name} restocked successfully! "
                f"Current stock: {product.stock}"
            )

    except (ValueError, TypeError):
        messages.error(request, "Please enter a valid quantity.")

    return redirect("restock_page")


def skin(request):

    category = request.GET.get('category', '')

    if category:
        products = Product.objects.filter(
            category__name__iexact=category
        ).order_by('-id')

    else:
        products = Product.objects.filter(
            category__name__in=[
                'Cleanser',
                'Moisturizer',
                'Serum',
                'Sunscreen'
            ]
        ).order_by('-id')

    best_sellers = Product.objects.filter(
        category__name__in=[
            'Cleanser',
            'Moisturizer',
            'Serum',
            'Sunscreen'
        ],
        stock__gt=0
    ).order_by('-id')[:4]

    makeup_products = Product.objects.filter(
        category__name__iexact='Makeup'
    )

    return render(request, 'skin.html', {
        'products': products,
        'best_sellers': best_sellers,
        'makeup_products': makeup_products,
    })

def product_variants(request):

    products = Product.objects.all()
    variants = ProductVariant.objects.select_related('product').all()

    if request.method == "POST":

        form = ProductVariantForm(request.POST, request.FILES)
        product_id = request.POST.get('product')

        if form.is_valid() and product_id:

            variant = form.save(commit=False)
            variant.product_id = product_id
            variant.save()

            return redirect('product_variants')

    else:
        form = ProductVariantForm()

    return render(request, 'product_variants.html', {
        'products': products,
        'variants': variants,
        'form': form,
    })
def hair(request):

    category = request.GET.get('category')

    if category:

        products = Product.objects.filter(
            category__name__iexact=category
        ).order_by('-id')

    else:

        products = Product.objects.filter(
            category__name__in=[
                'Shampoo',
                'Conditioner',
                'Hair Masks',
                'Hair Oils'
            ]
        ).order_by('-id')

    return render(request, 'hair.html', {
        'products': products,
        'selected_category': category
    })
def fragrance(request):

    fragrance_products = Product.objects.filter(
        category__name__iexact="Fragrance"
    )

    context = {
        "fragrance_products": fragrance_products,
    }

    return render(request, "fragrance.html", context)
def gifts_combos(request):

    gift_products = Product.objects.filter(
        category__name__in=[
            "Gifts & Combos",
            "Birthdays",
            "Anniversary",
            "Self Care",
            "Special Moments"
        ]
    ).order_by("-id")

    selected_category = request.GET.get("category", "").strip()
    selected_budget = request.GET.get("budget", "").strip()

    # Occasion category filter
    if selected_category:
        gift_products = gift_products.filter(
            category__name__iexact=selected_category
        )

    # Budget filter
    if selected_budget == "under499":
        gift_products = gift_products.filter(price__lt=499)

    elif selected_budget == "under999":
        gift_products = gift_products.filter(price__lt=999)

    elif selected_budget == "above1499":
        gift_products = gift_products.filter(price__gt=1499)

    elif selected_budget == "above2499":
        gift_products = gift_products.filter(price__gt=2499)

    context = {
        "gift_products": gift_products,
        "selected_category": selected_category,
        "selected_budget": selected_budget,
    }

    return render(request, "gifts_combos.html", context)
def new_arrivals(request):
    category = request.GET.get('category', '')

    products = Product.objects.all().order_by('-id')

    if category:
        products = products.filter(
            category__name__iexact=category
        )

    context = {
        'new_arrivals': products if category else products[:8],
        'selected_category': category,
    }

    return render(request, 'new_arrivals.html', context)

def customer_login(request):

    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":

        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        User = get_user_model()

        user_obj = User.objects.filter(
            email__iexact=email,
            is_staff=False,
            is_superuser=False
        ).first()

        if user_obj:

            user = authenticate(
                request,
                username=user_obj.get_username(),
                password=password
            )

            if user is not None:

                login(request, user)

                next_url = request.GET.get("next")

                if next_url:
                    return redirect(next_url)

                return redirect("home")

        messages.error(request, "Invalid email or password.")

    return render(request, "customer_login.html")


@login_required(login_url="/login/")
def customer_profile(request):
    return render(request, "customer_profile.html")


def customer_logout(request):
    logout(request)
    return redirect("home")

def customer_register(request):

    if request.method == "POST":

        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not all([full_name, email, phone, password, confirm_password]):

            messages.error(request, "Please fill in all fields.")

        elif User.objects.filter(email__iexact=email).exists():

            messages.error(request, "This email is already registered.")

        elif password != confirm_password:

            messages.error(request, "Passwords do not match.")

        else:

            try:

                validate_password(password)

                username = email

                if User.objects.filter(username=username).exists():

                    messages.error(request, "This account already exists.")

                else:

                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=full_name
                    )

                    # Save phone in session
                    request.session["registered_phone"] = phone

                    messages.success(
                        request,
                        "Account created successfully! Please log in."
                    )

                    return redirect("customer_login")

            except ValidationError as error:

                for message in error.messages:
                    messages.error(request, message)

    return render(request, "customer_register.html")
@login_required
def delivery_tracking(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    if order.expected_delivery is None:
        order.expected_delivery = (
            order.order_date.date() + timedelta(days=5)
        )
        order.save(update_fields=["expected_delivery"])

    items = order.items.all()

    statuses = [
        "Order Placed",
        "Order Confirmed",
        "Shipped",
        "Out for Delivery",
        "Delivered"
    ]

    return render(request, "delivery_tracking.html", {
        "order": order,
        "items": items,
        "statuses": statuses,
        "current_status_index": (
            statuses.index(order.delivery_status)
            if order.delivery_status in statuses
            else 0
        ),
        "today": timezone.localdate()
    })
@login_required
def track_order(request):
    if request.method == "POST":
        order_id = request.POST.get("order_id")

        order = Order.objects.filter(
            id=order_id,
            user=request.user
        ).first()

        if order:
            return redirect("delivery_tracking", order_id=order.id)

        return render(request, "track_order.html", {
            "error": "Invalid Order ID."
        })

    return render(request, "track_order.html")

@login_required
def my_orders(request):

    orders = Order.objects.filter(
        user=request.user
    ).prefetch_related("items").order_by("-order_date")

    delivered_count = orders.filter(
        delivery_status="Delivered"
    ).count()

    active_count = orders.exclude(
        delivery_status="Delivered"
    ).count()

    return render(request, "my_orders.html", {
        "orders": orders,
        "delivered_count": delivered_count,
        "active_count": active_count,
    })

@login_required
@require_POST
def cancel_order(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    if order.delivery_status in ["Order Placed", "Processing"]:
        order.delivery_status = "Cancelled"
        order.save()

        messages.success(request, "Order cancelled successfully!")
    else:
        messages.error(request, "This order cannot be cancelled.")

    return redirect("my_orders")

def search_products(request):
    query = request.GET.get('q', '').strip()

    products = Product.objects.none()

    if query:
        products = Product.objects.filter(
            name__icontains=query
        )

    return render(request, 'search_results.html', {
        'products': products,
        'query': query
    })

@login_required
def customer_dashboard(request):
    profile, created = CustomerProfile.objects.get_or_create(
        user=request.user
    )

    return render(request, "customer_dashboard.html", {
        "profile": profile
    })

@login_required(login_url='customer_login') 
def edit_profile(request): 
    user = request.user # Get or create the user's profile 
    profile, created = CustomerProfile.objects.get_or_create( user=user ) 
    if request.method == "POST": 
        first_name = request.POST.get('first_name', '').strip() 
        last_name = request.POST.get('last_name', '').strip() 
        email = request.POST.get('email', '').strip() 
        # Get uploaded profile photo
        photo = request.FILES.get('profile_photo') 
        User = get_user_model() 
        # Check email
        if not email:
            messages.error(request, "Email cannot be empty.") 
        elif User.objects.filter(email=email).exclude(pk=user.pk).exists(): 
            messages.error(request, "This email is already registered.") 
        else: 
            # Update user details
            user.first_name = first_name 
            user.last_name = last_name 
            user.email = email 
            user.save() 
            # Save profile photo if a new photo was selected
            if photo: 
                profile.profile_photo = photo 
                profile.save() 
            messages.success( request, "Profile updated successfully! 💗" ) 
            return redirect('edit_profile') 
    return render(request, 'edit_profile.html', { 'user': user, 'profile': profile, })

@login_required
def track_latest_order(request):

    order = Order.objects.filter(
        user=request.user
    ).order_by("-order_date").first()

    if order:
        return redirect("delivery_tracking", order_id=order.id)

    return redirect("my-orders")

def bridal_bundle(request): 
    occasion = request.GET.get('occasion', '').strip().lower() 
    print("Selected occasion:", occasion) 
    if occasion == 'wedding_day': 
        products = Product.objects.filter( 
            category__name__iexact='Wedding' ) 
        heading = 'Wedding Day Collection' 
    elif occasion == 'mehendi': 
        products = Product.objects.filter( 
            category__name__iexact='Mehendi' ) 
        heading = 'Mehendi Collection' 
    elif occasion == 'sangeet': 
        products = Product.objects.filter( 
            category__name__iexact='Sangeet' ) 
        heading = 'Sangeet Collection' 
    elif occasion == 'reception': 
        products = Product.objects.filter( 
            category__name__iexact='Reception' ) 
        heading = 'Reception Collection' 
    elif occasion == 'haldi': 
        products = Product.objects.filter( 
            category__name__iexact='Haldi' ) 
        heading = 'Haldi Collection' 
    elif occasion == 'honeymoon': 
        products = Product.objects.filter( 
            category__name__iexact='Honeymoon' ) 
        heading = 'Honeymoon Collection' 
    else: 
        products = Product.objects.filter( 
            category__name__iexact='Bridal Bundle' ) 
        heading = 'Bridal Bundle Collection' 
    print("Products count:", products.count()) 
    return render(request, 'bridal_bundle.html', { 
        'products': products, 
        'selected_occasion': occasion, 
        'heading': heading, })

def all_offers(request):

    now = timezone.now()

    # Active offers mattum display aagum
    products = Product.objects.filter(
        offer_price__isnull=False,
        offer_price__gt=0,
        offer_price__lt=F('price'),
        offer_start_date__lte=now,
        offer_end_date__gte=now
    ).select_related('category').order_by('offer_end_date')
    products = products.prefetch_related('variants')

    # Category filter
    selected_category = request.GET.get('category', '')

    if selected_category:
        products = products.filter(
            category__id=selected_category
        )

    # Discount filter
    selected_discount = request.GET.get('discount', '')

    if selected_discount == '10':
        products = products.filter(
            offer_price__lte=F('price') * 0.90
        )

    elif selected_discount == '20':
        products = products.filter(
            offer_price__lte=F('price') * 0.80
        )

    elif selected_discount == '30':
        products = products.filter(
            offer_price__lte=F('price') * 0.70
        )

    elif selected_discount == '40':
        products = products.filter(
            offer_price__lte=F('price') * 0.60
        )

    # Minimum price filter
    min_price = request.GET.get('min_price', '')

    if min_price:
        try:
            products = products.filter(
                offer_price__gte=float(min_price)
            )
        except ValueError:
            pass

    # Maximum price filter
    max_price = request.GET.get('max_price', '')

    if max_price:
        try:
            products = products.filter(
                offer_price__lte=float(max_price)
            )
        except ValueError:
            pass

    # Availability filter
    availability = request.GET.get('availability', '')

    if availability == 'in_stock':
        products = products.filter(stock__gt=0)

    elif availability == 'out_of_stock':
        products = products.filter(stock=0)

    # Sorting
    sort_by = request.GET.get('sort', '')

    if sort_by == 'price_low':
        products = products.order_by('offer_price')

    elif sort_by == 'price_high':
        products = products.order_by('-offer_price')

    elif sort_by == 'discount':
        products = products.order_by('offer_price')

    # Categories available in the offer products
    categories = Category.objects.filter(
        products__offer_price__isnull=False,
        products__offer_start_date__lte=now,
        products__offer_end_date__gte=now
    ).distinct()

    # Deals of the day
    deals = Product.objects.filter(
        offer_price__isnull=False,
        offer_price__gt=0,
        offer_price__lt=F('price'),
        offer_start_date__lte=now,
        offer_end_date__gte=now
    ).order_by('offer_end_date')[:8]

    context = {
        'products': products,
        'deals': deals,
        'categories': categories,
        'selected_category': selected_category,
        'selected_discount': selected_discount,
        'min_price': min_price,
        'max_price': max_price,
        'availability': availability,
        'sort_by': sort_by,
    }

    return render(request, 'all_offers.html', context)

def brushes_tools(request):

    # Main category and its subcategories
    category_names = [
        "Brushes & Tools",
        "Makeup Brushes",
        "Beauty Sponges",
        "Brush Sets",
        "Beauty Tools"
    ]

    # Get all these categories
    categories = Category.objects.filter(
        name__in=category_names
    )

    # Default: display products from all five categories
    products = Product.objects.filter(
        category__name__in=category_names
    ).order_by("-id")

    # Dropdown category filter
    selected_category = request.GET.get("category", "")

    if selected_category:
        products = products.filter(
            category__name__iexact=selected_category
        )

    # Product search
    search_query = request.GET.get("search", "").strip()

    if search_query:
        products = products.filter(
            name__icontains=search_query
        )

    # Price sorting
    sort_by = request.GET.get("sort", "")

    if sort_by == "low":
        products = products.order_by("price")

    elif sort_by == "high":
        products = products.order_by("-price")

    elif sort_by == "new":
        products = products.order_by("-id")

    return render(request, "brushes_tools.html", {
        "products": products,
        "categories": categories,
        "selected_category": selected_category,
        "search_query": search_query,
        "sort_by": sort_by,
    })


@staff_member_required(login_url="/admin-login/")
def admin_orders(request):

    # Get all orders
    orders = Order.objects.all().order_by('-order_date')

    # Get selected status
    status = request.GET.get('status', 'all').strip().lower()

    # Status mapping
    status_mapping = {
        'ordered': 'Order Placed',
        'accepted': 'Accepted',
        'shipped': 'Shipped',
        'delivered': 'Delivered',
        'cancelled': 'Cancelled',
    }

    # Filter by status
    if status in status_mapping:
        orders = orders.filter(
            delivery_status__iexact=status_mapping[status]
        )

    # Search by customer name, phone or order ID
    search = request.GET.get('search', '').strip()

    if search:
        filters = (
            Q(full_name__icontains=search) |
            Q(phone__icontains=search)
        )

        if search.isdigit():
            filters |= Q(id=int(search))

        orders = orders.filter(filters)

    # Filter by payment method
    payment = request.GET.get('payment', '').strip()

    if payment:
        orders = orders.filter(payment__iexact=payment)

    # Filter by starting date
    date_from = request.GET.get('date_from', '').strip()

    if date_from:
        orders = orders.filter(
            order_date__date__gte=date_from
        )

    # Filter by ending date
    date_to = request.GET.get('date_to', '').strip()

    if date_to:
        orders = orders.filter(
            order_date__date__lte=date_to
        )

    context = {
        'orders': orders,
        'status': status,
        'search': search,
        'payment': payment,
        'date_from': date_from,
        'date_to': date_to,
    }

    return render(
        request,
        'admin_orders.html',
        context
    )

@staff_member_required(login_url='/login/')
def admin_payments(request):

    orders = Order.objects.all().order_by('-order_date')

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    method = request.GET.get('method', '').strip()

    # Search
    if search:
        filters = (
            Q(full_name__icontains=search)
            | Q(phone__icontains=search)
        )

        if search.isdigit():
            filters |= Q(id=int(search))

        orders = orders.filter(filters)

    # Payment status filter
    if status in ['Paid', 'Pending', 'Failed', 'Refunded']:
        orders = orders.filter(payment_status=status)

    # Payment method filter
    if method:
        orders = orders.filter(payment__iexact=method)

    # Dashboard statistics
    all_orders = Order.objects.all()

    paid_orders = all_orders.filter(payment_status='Paid')

    total_revenue = (
        paid_orders.aggregate(total=Sum('total_amount'))['total']
        or Decimal('0.00')
    )

    context = {
        'orders': orders,
        'search': search,
        'selected_status': status,
        'selected_method': method,
        'total_revenue': total_revenue,
        'total_orders': all_orders.count(),
        'successful_payments': paid_orders.count(),
        'pending_payments': all_orders.filter(
            payment_status='Pending'
        ).count(),
        'failed_payments': all_orders.filter(
            payment_status='Failed'
        ).count(),
    }

    return render(request, 'admin_payments.html', context)

@login_required
@user_passes_test(admin_check, login_url='home')
def coupons(request):
    coupon_list = Coupon.objects.all().order_by('-id')

    return render(request, 'coupons.html', {
        'coupons': coupon_list
    })


@login_required
@user_passes_test(admin_check, login_url='home')
def add_coupon(request):
    if request.method == 'POST':
        form = CouponForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon created successfully!')
            return redirect('coupons')
    else:
        form = CouponForm()

    return render(request, 'coupon_form.html', {
        'form': form,
        'title': 'Add Coupon'
    })


@login_required
@user_passes_test(admin_check, login_url='home')
def edit_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)

    if request.method == 'POST':
        form = CouponForm(request.POST, instance=coupon)

        if form.is_valid():
            form.save()
            messages.success(request, 'Coupon updated successfully!')
            return redirect('coupons')
    else:
        form = CouponForm(instance=coupon)

    return render(request, 'coupon_form.html', {
        'form': form,
        'title': 'Edit Coupon'
    })


@login_required
@user_passes_test(admin_check, login_url='home')
def delete_coupon(request, coupon_id):
    coupon = get_object_or_404(Coupon, id=coupon_id)

    if request.method == 'POST':
        coupon.delete()
        messages.success(request, 'Coupon deleted successfully!')

    return redirect('coupons')

def lip(request):

    products = Product.objects.filter(
        category__name__iexact="Lipstick"
    ).prefetch_related("variants").order_by("-id")

    return render(request, "lip.html", {
        "products": products
    })

@login_required
@user_passes_test(admin_check, login_url="home")
def admin_customers(request):

    customers = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        last_login__isnull=False
    ).order_by("-last_login")

    search = request.GET.get("search", "").strip()

    if search:
        customers = customers.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    total_customers = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        last_login__isnull=False
    ).count()

    active_customers = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        last_login__isnull=False,
        is_active=True
    ).count()

    context = {
        "customers": customers,
        "total_customers": total_customers,
        "active_customers": active_customers,
        "search": search,
    }

    return render(request, "admin_customers.html", context)

@login_required
@user_passes_test(admin_check, login_url="home")
def admin_reports(request):

    # --------------------------------
    # BASIC DETAILS
    # --------------------------------

    orders = Order.objects.all()

    total_orders = orders.count()

    total_revenue = orders.aggregate(
        total=Sum("total_amount")
    )["total"] or 0

    total_customers = User.objects.filter(
        is_staff=False,
        is_superuser=False
    ).count()

    total_products = Product.objects.count()

    today = timezone.localdate()

    # --------------------------------
    # MONTHLY REVENUE - LAST 6 MONTHS
    # --------------------------------

    start_month = (
        today.replace(day=1) - timedelta(days=150)
    ).replace(day=1)

    monthly_revenue = (
        Order.objects.filter(
            order_date__date__gte=start_month,
            order_date__date__lte=today
        )
        .annotate(month=TruncMonth("order_date"))
        .values("month")
        .annotate(revenue=Sum("total_amount"))
        .order_by("month")
    )

    # --------------------------------
    # TOP SELLING PRODUCTS
    # --------------------------------

    top_products = (
        OrderItem.objects
        .values("name")
        .annotate(quantity_sold=Sum("quantity"))
        .order_by("-quantity_sold")[:5]
    )

    # --------------------------------
    # ORDER STATUS ANALYSIS
    # --------------------------------

    order_status_data = (
        Order.objects
        .values("delivery_status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    for status in order_status_data:
        if total_orders > 0:
            status["percentage"] = (
                status["count"] / total_orders
            ) * 100
        else:
            status["percentage"] = 0

    # --------------------------------
    # PAYMENT ANALYSIS
    # --------------------------------

    payment_summary = (
        Order.objects
        .values("payment")
        .annotate(
            count=Count("id"),
            revenue=Sum("total_amount")
        )
        .order_by("-count")
    )

    # --------------------------------
    # CUSTOMER GROWTH
    # --------------------------------

    customer_growth = (
        User.objects.filter(
            is_staff=False,
            is_superuser=False
        )
        .annotate(month=TruncMonth("date_joined"))
        .values("month")
        .annotate(customer_count=Count("id"))
        .order_by("month")
    )

    # --------------------------------
    # DAILY REVENUE - LAST 7 DAYS
    # --------------------------------

    start_date = today - timedelta(days=6)

    daily_revenue = (
        Order.objects.filter(
            order_date__date__gte=start_date,
            order_date__date__lte=today
        )
        .annotate(day=TruncDate("order_date"))
        .values("day")
        .annotate(revenue=Sum("total_amount"))
        .order_by("day")
    )

    # --------------------------------
    # CHART DATA
    # --------------------------------

    monthly_labels = [
        item["month"].strftime("%b %Y")
        for item in monthly_revenue
    ]

    monthly_values = [
        float(item["revenue"] or 0)
        for item in monthly_revenue
    ]

    customer_labels = [
        item["month"].strftime("%b %Y")
        for item in customer_growth
    ]

    customer_values = [
        item["customer_count"]
        for item in customer_growth
    ]

    daily_labels = [
        item["day"].strftime("%d %b")
        for item in daily_revenue
    ]

    daily_values = [
        float(item["revenue"] or 0)
        for item in daily_revenue
    ]

    # --------------------------------
    # CONTEXT
    # --------------------------------

    context = {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "total_customers": total_customers,
        "total_products": total_products,

        "top_products": top_products,
        "order_status_data": order_status_data,
        "payment_summary": payment_summary,

        "monthly_labels_json": monthly_labels,
        "monthly_values_json": monthly_values,

        "customer_labels_json": customer_labels,
        "customer_values_json": customer_values,

        "daily_labels_json": daily_labels,
        "daily_values_json": daily_values,
    }

    return render(request, "admin_reports.html", context)

@login_required
@user_passes_test(admin_check, login_url="home")
def admin_users(request):

    # Admin users only
    users = User.objects.filter(
        is_staff=True
    ).order_by("-date_joined")

    search = request.GET.get("search", "").strip()

    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    total_users = users.count()

    active_users = users.filter(
        is_active=True
    ).count()

    staff_users = users.filter(
        is_staff=True
    ).count()

    context = {
        "users": users,
        "total_users": total_users,
        "active_users": active_users,
        "staff_users": staff_users,
        "search": search,
    }

    return render(request, "admin_users.html", context)
@login_required(login_url='/login/')
@require_POST
def verify_payment(request):

    order_id = request.POST.get("order_id")
    payment_id = request.POST.get("razorpay_payment_id")
    razorpay_order_id = request.POST.get("razorpay_order_id")
    signature = request.POST.get("razorpay_signature")

    if not all([order_id, payment_id, razorpay_order_id, signature]):
        return JsonResponse({
            "success": False,
            "message": "Missing payment details."
        })

    try:
        client = razorpay.Client(
            auth=(
                settings.RAZORPAY_KEY_ID,
                settings.RAZORPAY_KEY_SECRET
            )
        )

        with transaction.atomic():

            order = Order.objects.select_for_update().get(
                id=order_id,
                user=request.user,
                payment_order_id=razorpay_order_id
            )

            # Already paid - avoid duplicate stock reduction
            if order.payment_status == "Paid":
                return JsonResponse({
                    "success": True,
                    "redirect_url": reverse(
                        "delivery_tracking",
                        args=[order.id]
                    )
                })

            # VERIFY SIGNATURE
            client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature
            })

            # VERIFY PAYMENT DETAILS
            payment_details = client.payment.fetch(payment_id)

            if payment_details.get("status") != "captured":
                return JsonResponse({
                    "success": False,
                    "message": "Payment is not captured yet."
                })

            if payment_details.get("order_id") != razorpay_order_id:
                return JsonResponse({
                    "success": False,
                    "message": "Payment order mismatch."
                })

            if payment_details.get("amount") != int(order.total_amount * 100):
                return JsonResponse({
                    "success": False,
                    "message": "Payment amount mismatch."
                })

            if payment_details.get("currency") != "INR":
                return JsonResponse({
                    "success": False,
                    "message": "Invalid payment currency."
                })

            # REDUCE STOCK AFTER VERIFIED PAYMENT
            for item in order.items.all():

                if item.variant:

                    variant = ProductVariant.objects.select_for_update().get(
                        id=item.variant.id
                    )

                    if variant.stock < item.quantity:
                        order.delivery_status = "Stock Review Required"
                        order.payment_status = "Paid"
                        order.payment_transaction_id = payment_id
                        order.save()

                        return JsonResponse({
                            "success": False,
                            "message": "Payment received. Please contact support regarding stock availability."
                        })

                    variant.stock -= item.quantity
                    variant.save(update_fields=["stock"])

                elif item.product:

                    product = Product.objects.select_for_update().get(
                        id=item.product.id
                    )

                    if product.stock < item.quantity:
                        order.delivery_status = "Stock Review Required"
                        order.payment_status = "Paid"
                        order.payment_transaction_id = payment_id
                        order.save()

                        return JsonResponse({
                            "success": False,
                            "message": "Payment received. Please contact support regarding stock availability."
                        })

                    product.stock -= item.quantity
                    product.save(update_fields=["stock"])

            # UPDATE PAYMENT STATUS
            order.payment_status = "Paid"
            order.payment_transaction_id = payment_id
            order.save(update_fields=[
                "payment_status",
                "payment_transaction_id"
            ])

        # CLEAR SESSION
        request.session.pop("order_product_id", None)
        request.session.pop("order_variant_id", None)
        request.session.pop("order_product_quantity", None)
        request.session.pop("applied_coupon", None)

        return JsonResponse({
            "success": True,
            "redirect_url": reverse(
                "delivery_tracking",
                args=[order.id]
            )
        })

    except Order.DoesNotExist:
        return JsonResponse({
            "success": False,
            "message": "Order not found."
        })

    except Exception:
        return JsonResponse({
            "success": False,
            "message": "Payment verification failed. Please contact support."
        })
def payment_failed(request):
    pass