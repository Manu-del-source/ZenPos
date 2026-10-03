from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, Count, F
from django.utils import timezone
from datetime import timedelta
from .models import Product, Sale, Customer, User, StockAdjustment
from .serializers import (ProductSerializer, SaleSerializer, CustomerSerializer, UserSerializer, StockAdjustmentSerializer)

from django.http import HttpResponse

def landing_page(request):
    html = """
    <html>
        <head><title>ZenPOS Back-Office</title></head>
        <body style="font-family: sans-serif; padding: 50px; text-align: center; background: #f4f7f6;">
            <h1 style="color: #2c3e50;">🛒 ZenPOS Back-Office 🇰🇪</h1>
            <p style="color: #7f8c8d;">The system is online and ready.</p>
            <div style="margin-top: 30px;">
                <a href="/admin/" style="background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 10px;">Go to Admin Panel</a>
                <a href="/api/v2/" style="background: #2ecc71; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 10px;">Browse API</a>
            </div>
            <p style="margin-top: 50px; font-size: 0.8em; color: #bdc3c7;">Running on Django with REST Framework</p>
        </body>
    </html>
    """
    return HttpResponse(html)

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    @action(detail=False, methods=['get'])
    def search(self, req):
        barcode = req.query_params.get('barcode')
        if barcode:
            product = Product.objects.filter(barcode=barcode).first()
            if product:
                return Response(ProductSerializer(product).data)
        return Response({'message': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer

    def perform_create(self, serializer):
        serializer.save(cashier=self.request.user)

    @action(detail=False, methods=['get'])
    def reports(self, req):
        range_type = req.query_params.get('range', 'today')
        
        now = timezone.now()
        if range_type == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif range_type == 'weekly':
            start_date = now - timedelta(days=7)
        elif range_type == 'monthly':
            start_date = now - timedelta(days=30)
        else:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        sales = Sale.objects.filter(created_at__gte=start_date)
        
        total_revenue = sales.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_sales = sales.count()
        
        # Top products
        from .models import SaleItem
        top_products = SaleItem.objects.filter(sale__created_at__gte=start_date)\
            .values('product__name')\
            .annotate(total_sold=Sum('quantity'), revenue=Sum('subtotal'))\
            .order_by('-total_sold')[:5]

        return Response({
            'total_revenue': total_revenue,
            'total_sales': total_sales,
            'top_products': top_products
        })

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    @action(detail=False, methods=['get'])
    def search(self, req):
        phone = req.query_params.get('phone')
        if phone:
            customer = Customer.objects.filter(phone=phone).first()
            if customer:
                return Response(CustomerSerializer(customer).data)
        return Response({'message': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

class StockAdjustmentViewSet(viewsets.ModelViewSet):
    queryset = StockAdjustment.objects.all()
    serializer_class = StockAdjustmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class AnalyticsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAdminUser]

    @action(detail=False, methods=['get'])
    def daily_sales_trend(self, req):
        # Last 30 days of sales
        from django.db.models.functions import TruncDate
        data = Sale.objects.annotate(date=TruncDate('created_at'))\
            .values('date')\
            .annotate(revenue=Sum('total_amount'), count=Count('id'))\
            .order_by('date')
        return Response(data)

    @action(detail=False, methods=['get'])
    def stock_value(self, req):
        # Total capital tied in inventory
        total_value = Product.objects.aggregate(
            total=Sum(F('stock_level') * F('cost_price'))
        )
        return Response(total_value)

    @action(detail=False, methods=['get'])
    def inventory_status(self, req):
        # Count of low stock items
        low_stock = Product.objects.filter(stock_level__lte=F('low_stock_threshold')).count()
        total_products = Product.objects.count()
        return Response({
            'low_stock_count': low_stock,
            'total_products': total_products
        })
