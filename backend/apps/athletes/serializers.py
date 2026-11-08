"""Sérialiseurs de la feature 03 (app ``athletes``).

L'email du propriétaire n'est exposé qu'à ce dernier : un coach ou une équipe
qui voient le profil d'un sportif via un grant actif ne reçoivent pas son
adresse email (donnée personnelle, cf. règle « données privées par défaut »).
"""

from rest_framework import serializers

from apps.athletes.models import AthleteProfile


class AthleteProfileSerializer(serializers.ModelSerializer):
    """Profil sportif ; ``email`` est uniquement renseigné pour le propriétaire."""

    email = serializers.SerializerMethodField()

    class Meta:
        model = AthleteProfile
        fields = (
            "id",
            "email",
            "date_of_birth",
            "sex",
            "height_cm",
            "weight_kg",
            "dominant_side",
            "sport",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "email", "created_at", "updated_at")

    def get_email(self, obj) -> str | None:
        request = self.context.get("request")
        if request is not None and getattr(request.user, "pk", None) == obj.user_id:
            return obj.user.email
        return None


class CreateAthleteSerializer(serializers.Serializer):
    """Création à la demande du profil sportif de l'utilisateur connecté."""

    date_of_birth = serializers.DateField()
    sex = serializers.ChoiceField(
        choices=AthleteProfile.Sex.choices, required=False, allow_blank=True
    )
    height_cm = serializers.IntegerField(
        min_value=1, max_value=300, required=False, allow_null=True
    )
    weight_kg = serializers.IntegerField(
        min_value=1, max_value=500, required=False, allow_null=True
    )
    dominant_side = serializers.ChoiceField(
        choices=AthleteProfile.DominantSide.choices, required=False, allow_blank=True
    )
    sport = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_date_of_birth(self, value):
        from django.utils import timezone

        if value > timezone.now().date():
            raise serializers.ValidationError("La date de naissance ne peut pas être future.")
        return value
