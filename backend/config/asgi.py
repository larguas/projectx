"""Application ASGI.

Reste un ASGI Django classique pour l'instant ; les WebSocket
(Django Channels) arrivent avec la feature 10.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_asgi_application()
