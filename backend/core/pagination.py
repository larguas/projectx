"""Pagination par défaut de l'API : page numérotée sur toutes les listes."""

from django.conf import settings
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = settings.DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = 200
