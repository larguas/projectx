"""Tests du nettoyage des champs sensibles avant envoi à Sentry."""

from core.sentry import FILTERED_VALUE, scrub_event


def test_sensitive_fields_are_filtered():
    event = {
        "request": {
            "headers": {"Authorization": "Bearer abc", "Host": "api.example.com"},
            "query_string": "page=1",
        },
        "breadcrumbs": [{"data": {"password": "s3cret", "user_id": 7}}],
        "extra": {"access_token": "tok-1", "samples": [1, 2, 3]},
    }
    scrubbed = scrub_event(event)
    # En-tête d'autorisation et jetons masqués...
    assert scrubbed["request"]["headers"]["Authorization"] == FILTERED_VALUE
    assert scrubbed["breadcrumbs"][0]["data"]["password"] == FILTERED_VALUE
    assert scrubbed["extra"]["access_token"] == FILTERED_VALUE
    # ...y compris les samples de signaux bruts.
    assert scrubbed["extra"]["samples"] == FILTERED_VALUE
    # Les champs non sensibles sont conservés tels quels.
    assert scrubbed["request"]["headers"]["Host"] == "api.example.com"
    assert scrubbed["breadcrumbs"][0]["data"]["user_id"] == 7


def test_scrub_event_handles_none():
    assert scrub_event(None) is None
