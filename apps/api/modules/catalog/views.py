from django.db import models
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.core.mixins import OrganizationScopedMixin

from .models import Brand, Category, PriceHistory, Product, ProductBarcode, TaxRate, Unit
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    PriceHistorySerializer,
    ProductBarcodeSerializer,
    ProductSerializer,
    TaxRateSerializer,
    UnitSerializer,
)

# Reading the catalogue needs products.view; adding to it needs products.create;
# changing it - including a price, which is recorded in price_history - needs
# products.update. Categories, brands, units and tax rates are catalogue masters
# and share these codes rather than carrying a set of their own: they are rows a
# product points at, not separately privileged objects.
CATALOGUE_VIEW = ("products.view",)
CATALOGUE_WRITE_PERMISSIONS = {
    "create": ("products.create",),
    "update": ("products.update",),
    "partial_update": ("products.update",),
    "destroy": ("products.update",),
}


class ProductViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    required_permissions = CATALOGUE_VIEW
    required_permissions_by_action = CATALOGUE_WRITE_PERMISSIONS

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("category", "brand", "unit", "tax_rate")
            .prefetch_related("barcodes")
        )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(sku__icontains=search)
            )

        return queryset

    def _barcode_queryset(self):
        """Barcodes the caller may resolve, scoped the same way products are."""
        queryset = ProductBarcode.objects.select_related("product")

        if getattr(self.request.user, "is_superuser", False):
            return queryset

        organization = self.get_organization()
        if organization is None:
            return queryset.none()

        return queryset.filter(organization=organization)

    @action(detail=False, methods=["get"])
    def search(self, request):
        """Resolve a scanned barcode to a single product."""
        barcode = request.query_params.get("barcode")
        if barcode:
            match = self._barcode_queryset().filter(barcode=barcode).first()
            if match:
                return Response(ProductSerializer(match.product).data)

        # USB scanners often send the product SKU rather than a row in the
        # optional ProductBarcode table. Treat an exact SKU as a barcode hit too.
        if barcode:
            product = self.get_queryset().filter(sku=barcode, is_active=True).first()
            if product:
                return Response(ProductSerializer(product).data)

        return Response(
            {"detail": "Product not found."},
            status=status.HTTP_404_NOT_FOUND,
        )


class CategoryViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Category.objects.select_related("parent").all()
    serializer_class = CategorySerializer

    required_permissions = CATALOGUE_VIEW
    required_permissions_by_action = CATALOGUE_WRITE_PERMISSIONS


class BrandViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer

    required_permissions = CATALOGUE_VIEW
    required_permissions_by_action = CATALOGUE_WRITE_PERMISSIONS


class UnitViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer

    required_permissions = CATALOGUE_VIEW
    required_permissions_by_action = CATALOGUE_WRITE_PERMISSIONS


class TaxRateViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer

    required_permissions = CATALOGUE_VIEW
    required_permissions_by_action = CATALOGUE_WRITE_PERMISSIONS


class ProductBarcodeViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = ProductBarcode.objects.select_related("product").all()
    serializer_class = ProductBarcodeSerializer

    required_permissions = CATALOGUE_VIEW
    required_permissions_by_action = CATALOGUE_WRITE_PERMISSIONS


class PriceHistoryViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only: rows are written by the product serializer, not by clients."""

    queryset = PriceHistory.objects.select_related("product", "changed_by").all()
    serializer_class = PriceHistorySerializer
    organization_field = "product__organization"

    required_permissions = CATALOGUE_VIEW
