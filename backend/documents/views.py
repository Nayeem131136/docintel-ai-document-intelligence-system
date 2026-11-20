from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response


@api_view(["GET"])
@throttle_classes([])
def health(request):
    """Liveness / readiness probe. Reports database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        database = "ok"
    except Exception:  # noqa: BLE001 - report any DB failure as "unavailable"
        database = "unavailable"

    healthy = database == "ok"
    return Response(
        {
            "status": "ok" if healthy else "degraded",
            "service": "docintel-api",
            "database": database,
            "debug": settings.DEBUG,
        },
        status=200 if healthy else 503,
    )
