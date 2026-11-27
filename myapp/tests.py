from django.test import TestCase
from django.urls import reverse
from .models import Category, Product


class HomeViewTests(TestCase):
    def test_new_and_trending_shows_selected_category_by_default(self):
        selected_category = Category.objects.create(name="selected_category")
        other_category = Category.objects.create(name="Skincare")
        selected_product = Product.objects.create(
            name="Selected product",
            price="10.00",
            image="products/selected.jpg",
            category=selected_category,
        )
        Product.objects.create(
            name="Other product",
            price="12.00",
            image="products/other.jpg",
            category=other_category,
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["products"].values_list("id", flat=True)),
            [selected_product.id],
        )

    def test_home_can_filter_products_by_category_name_or_id(self):
        category = Category.objects.create(name="selected_category")
        product = Product.objects.create(
            name="Selected product",
            price="10.00",
            image="products/selected.jpg",
            category=category,
        )

        for category_value in (category.name, str(category.id)):
            with self.subTest(category=category_value):
                response = self.client.get(
                    reverse("home"),
                    {"category": category_value},
                )

                self.assertEqual(
                    list(response.context["products"].values_list("id", flat=True)),
                    [product.id],
                )
