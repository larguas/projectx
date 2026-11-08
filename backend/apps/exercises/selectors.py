"""Sélecteurs de lecture de la feature 05 (app ``exercises``).

Règles de visibilité de la bibliothèque d'exercices :
- un exercice ``is_global=True`` (bibliothèque partagée) est lisible par tout
  utilisateur authentifié ;
- un exercice personnel (``is_global=False``) n'est visible que par son
  créateur (``created_by``) — les autres utilisateurs reçoivent un 404,
  comme pour les capteurs de la feature 04 : l'existence n'est pas révélée ;
- un superutilisateur Django voit tout (usage opérationnel/administratif,
  même décision que la feature 03).

Définition du « staff » (documentée, exigence de la spec feature 05) :
l'écriture des exercices GLOBAUX est réservée au staff de la plateforme,
défini ici comme ``user.is_staff`` OU ``user.is_superuser`` — le drapeau
Django ``is_staff`` étant le marqueur « administrateur plateforme » du modèle
``accounts.User`` (les superusers y ont droit par cohérence avec l'accès
total accordé à ``core.access``). Les coachs et sportifs ne créent que des
exercices personnels.

Aucun contrôle de grant n'intervient ici : la bibliothèque n'est pas une
donnée d'un sportif (pas de passage par ``core.access``) ; les workouts liés
à un sportif, si, cf. ``apps.workouts.selectors``.
"""

from django.db.models import Q, QuerySet


def is_staff(user) -> bool:
    """Le « staff » plateforme : ``is_staff`` OU superutilisateur Django."""
    return bool(
        getattr(user, "is_authenticated", False) and (user.is_staff or user.is_superuser)
    )


def visible_exercises(user) -> QuerySet:
    """Exercices visibles par ``user`` (sélecteur de liste).

    Base de ``GET /api/v1/exercises/`` : exercices globaux + exercices
    personnels de l'utilisateur lui-même ; tout pour un superutilisateur.
    """
    from apps.exercises.models import Exercise

    qs = Exercise.objects.all()
    if user is None or not getattr(user, "is_authenticated", False):
        return qs.none()
    if user.is_superuser:
        return qs
    return qs.filter(Q(is_global=True) | Q(created_by=user)).distinct()


def can_read_exercise(user, exercise) -> bool:
    """Lecture d'un exercice : global → tout utilisateur authentifié ;
    personnel → créateur ou superutilisateur uniquement."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if exercise.is_global:
        return True
    return user.is_superuser or exercise.created_by_id == user.pk


def can_write_exercise(user, exercise) -> bool:
    """Écriture d'un exercice existant :

    - global → staff plateforme (``is_staff`` / superuser) uniquement ;
    - personnel → créateur uniquement (le staff ne modifie pas les données
      personnelles d'un autre utilisateur — privacy by default).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if exercise.is_global:
        return is_staff(user)
    return exercise.created_by_id == user.pk
