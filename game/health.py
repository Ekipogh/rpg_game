"""Readiness endpoint used by the local deployment helper."""
import json

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        manifest = settings.BASE_DIR / 'RELEASE.json'
        revision = json.loads(manifest.read_text())['revision'] if manifest.exists() else 'development'
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    response = JsonResponse({'status': 'ok', 'revision': revision})
    response['Cache-Control'] = 'no-store'
    return response
