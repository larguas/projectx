"""Vues de la feature 05 (app ``exercises``).

- ``GET /api/v1/muscle-groups/`` : catalogue des groupes musculaires, lecture
  seule pour tout utilisateur authentifié ;
- ``GET /api/v1/muscles/`` : catalogue des muscles (filtre par groupe +
  recherche texte), lecture seule ;
- ``GET/POST /api/v1/exercises/`` : liste des exercices visibles (sélecteur
  ``apps.exercises.selectors.visible_exercises`` — globaux + personnels du
  connecté) avec filtres (groupe musculaire, global/personnel, archivé, type
  de mouvement) et recherche texte ; la création est réservée à l'utilisateur
  connecté : staff → exercice global (bibliothèque), sinon personnel ;
- ``GET/PATCH/DELETE /api/v1/exercises/{id}/`` : détail visible selon
  ``selectors.can_read_exercise`` (404 sinon — l'existence n'est pas révélée,
  même convention que la feature 04) ; PATCH par le staff (global) ou le
  créateur (personnel) ; DELETE = suppression physique d'un exercice
  personnel, archivage logique d'un exercice global.

Aucun audit ici : contrairement aux capteurs (feature 04), la bibliothèque
n'est pas une donnée d'un sportif — il n'y a pas de lecture par grant à
tracer. Les lectures de workouts rattachés à un sportif sont auditées dans
l'app ``workouts``.
"""

from django_filters import rest_framework as filters
from rest_framework import exceptions, generics, permissions, status
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from apps.exercises import selectors, serializers, services
from core.exceptions import error_response

_ERROR_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
}


def _service_error(exc: services.ExercisesServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


class MuscleGroupListView(generics.ListAPIView):
    """Catalogue des groupes musculaires (lecture seule)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.MuscleGroupSerializer

    def get_queryset(self):
        from apps.exercises.models import MuscleGroup

        return MuscleGroup.objects.all()


class MuscleListView(generics.ListAPIView):
    """Catalogue des muscles (lecture seule) : filtre par groupe, recherche texte."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.MuscleSerializer
    filterset_fields = ("muscle_group",)
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    search_fields = ("name", "latin_name", "code")

    def get_queryset(self):
        from apps.exercises.models import Muscle

        return Muscle.objects.select_related("muscle_group").all()


class ExerciseListView(generics.ListCreateAPIView):
    """Liste des exercices visibles + création d'un exercice."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.ExerciseSerializer
    filterset_fields = ("is_global", "is_archived", "movement_type", "muscles__muscle_group")
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    search_fields = ("name", "description")

    def get_queryset(self):
        return (
            selectors.visible_exercises(self.request.user)
            .prefetch_related("muscle_links__muscle__muscle_group")
            .select_related("created_by")
        )

    def create(self, request, *args, **kwargs):
        serializer = serializers.CreateExerciseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            exercise = services.create_exercise(request.user, serializer.validated_data)
        except services.ExercisesServiceError as exc:
            return _service_error(exc)
        output = serializers.ExerciseSerializer(exercise, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class ExerciseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail d'un exercice visible + mise à jour / suppression selon les droits."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.ExerciseSerializer
    http_method_names = ["get", "patch", "delete"]  # pas de PUT : périmètre API

    def get_object(self):
        from apps.exercises.models import Exercise

        exercise = Exercise.objects.filter(pk=self.kwargs["pk"]).first()
        if exercise is None or not selectors.can_read_exercise(self.request.user, exercise):
            raise exceptions.NotFound("Exercice introuvable.")
        return exercise

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.UpdateExerciseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            exercise = services.update_exercise(request.user, instance, serializer.validated_data)
        except services.ExercisesServiceError as exc:
            return _service_error(exc)
        output = serializers.ExerciseSerializer(exercise, context={"request": request})
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            services.delete_or_archive_exercise(request.user, instance)
        except services.ExercisesServiceError as exc:
            return _service_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)
