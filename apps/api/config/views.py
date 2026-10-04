from django.db import connection
from django.http import HttpResponse, JsonResponse


def landing_page(request):
    """Minimal status page for smoke checks.

    The previous version linked to an API browser at ``/api/v2/``. That route
    no longer exists because module routers no longer register an API root.
    """
    return HttpResponse(
        """
        <html>
            <head><title>Kipchi POS API</title></head>
            <body style="font-family: sans-serif; padding: 50px;">
                <h1>Kipchi POS API</h1>
                <p>The service is running.</p>
                <p><a href="/admin/">Admin</a></p>
            </body>
        </html>
        """
    )


def health_check(request):
    """Render health probe: verifies the Django process and database are reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unhealthy", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})
