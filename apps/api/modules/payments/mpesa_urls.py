from django.urls import path

from . import views

# The secret segment is part of the URL Safaricom is given; it is validated in
# the view against MPESA_CALLBACK_SECRET and never logged.
urlpatterns = [
    path("mpesa/callback/<str:secret>/", views.mpesa_callback, name="mpesa-callback"),
]
