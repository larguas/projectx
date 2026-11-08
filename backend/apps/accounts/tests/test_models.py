"""Tests des modèles de la feature 02 (User, DeviceAuthorization)."""

import hashlib
import re

import pytest
from django.db import IntegrityError

from apps.accounts.models import DeviceAuthorization, User, generate_user_code, hash_code
from apps.accounts.tests.factories import UserFactory

USER_CODE_RE = re.compile(r"[A-HJ-KM-NP-Z2-9]{4}-[A-HJ-KM-NP-Z2-9]{4}")


class TestUser:
    def test_create_user_lowercases_email(self):
        user = User.objects.create_user("Foo.Bar@Example.COM", "S3cure-Passw0rd!-EMG")
        assert user.email == "foo.bar@example.com"

    def test_save_lowercases_email(self):
        user = UserFactory.build(email="UPPER@Case.Example")
        user.save()
        assert user.email == "upper@case.example"

    def test_create_user_requires_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user("", "S3cure-Passw0rd!-EMG")

    def test_duplicate_email_is_case_insensitive(self):
        UserFactory(email="dup@example.com")
        with pytest.raises(IntegrityError):
            User.objects.create_user("DUP@Example.COM", "S3cure-Passw0rd!-EMG")

    def test_superuser_defaults(self):
        user = User.objects.create_superuser("admin@emg.local", "S3cure-Passw0rd!-EMG")
        assert user.is_staff and user.is_superuser

    def test_username_field_is_email(self):
        assert User.USERNAME_FIELD == "email"


class TestDeviceAuthorization:
    def test_hash_code_is_sha256_hex(self):
        assert hash_code("abc") == hashlib.sha256(b"abc").hexdigest()

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (DeviceAuthorization.Status.APPROVED, True),
            (DeviceAuthorization.Status.CONSUMED, True),
            (DeviceAuthorization.Status.PENDING, False),
            (DeviceAuthorization.Status.DENIED, False),
            (DeviceAuthorization.Status.EXPIRED, False),
        ],
    )
    def test_is_active_authorization(self, status, expected):
        authorization = DeviceAuthorization(
            device_code_hash=hash_code("d"), user_code_hash=hash_code("u"), status=status
        )
        assert authorization.is_active_authorization is expected

    def test_user_code_format_and_alphabet(self):
        for _ in range(200):
            code = generate_user_code()
            assert USER_CODE_RE.fullmatch(code), code
            assert not set("ILO01") & set(code)

    def test_user_codes_are_unique(self):
        codes = {generate_user_code() for _ in range(1000)}
        assert len(codes) == 1000
