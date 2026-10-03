from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api import views
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

router = DefaultRouter()
router.register(r'products', views.ProductViewSet)
router.register(r'sales', views.SaleViewSet)
router.register(r'customers', views.CustomerViewSet)
router.register(r'adjustments', views.StockAdjustmentViewSet)
router.register(r'analytics', views.AnalyticsViewSet, basename='analytics')

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('admin/', admin.site.urls),
    path('api/v2/', include(router.urls)),
    path('api/v2/auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v2/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
