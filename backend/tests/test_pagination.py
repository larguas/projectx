"""Tests de la pagination par défaut (page numérotée)."""

from django.test import RequestFactory
from rest_framework.request import Request as APIRequest

from core.pagination import DefaultPagination


def _api_request(path: str):
    # La pagination DRF lit ``request.query_params`` : il faut un request enveloppé.
    return APIRequest(RequestFactory().get(path))


def test_default_page_size_and_response_shape():
    pagination = DefaultPagination()
    request = _api_request("/api/v1/items/")
    page = pagination.paginate_queryset(list(range(120)), request)
    assert len(page) == 50

    response = pagination.get_paginated_response([{"index": i} for i in page])
    data = response.data
    assert data["count"] == 120
    assert data["previous"] is None
    assert data["next"] is not None
    assert len(data["results"]) == 50


def test_page_size_query_param():
    pagination = DefaultPagination()
    request = _api_request("/api/v1/items/?page_size=10")
    page = pagination.paginate_queryset(list(range(25)), request)
    assert len(page) == 10
