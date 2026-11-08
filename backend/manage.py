#!/usr/bin/env python
"""Point d'entrée des commandes de gestion Django."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Impossible d'importer Django. Vérifiez que l'environnement uv est installé "
            "(make install) et que DJANGO_SETTINGS_MODULE pointe vers un module existant."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
