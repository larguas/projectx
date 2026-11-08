"""Vues de la feature 05 (app ``workouts``).

- ``GET/POST /api/v1/workouts/`` : liste des plans visibles (sélecteur
  ``apps.workouts.selectors.visible_workouts`` — plans du propriétaire +
  plans rattachés à ses sportifs couverts par un grant ``sessions:read``) et
  création d'un plan pour l'utilisateur connecté ;
- ``GET/PATCH/DELETE /api/v1/workouts/{id}/`` : détail visible selon
  ``selectors.can_read_workout`` (404 sinon — l'existence n'est pas révélée,
  même convention que la feature 04) ; PATCH et DELETE réservés à l'écriture
  (propriétaire ou grant ``sessions:write`` actif sur le sportif rattaché) ;
- ``PUT /api/v1/workouts/{id}/exercises/`` : remplacement ATOMIQUE de la
  liste ordonnée d'exercices (réindexée 1..N).

Audit (même principe que les features 03/04) : toute lecture par un
NON-propriétaire émet un événement (``workout.viewed`` / ``workout.listed``)
via ``apps.audit.services.record_event`` — c'est le traçage des lectures
coach/équipe exigé par la spec. La metadata ne contient que des compteurs,
aucune donnée personnelle ; l'audit de liste n'est émis que quand au moins un
plan non propriétaire est visible (comportement identique à ``devices``).
"""

from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response

from apps.audit.services import record_event
from apps.workouts import selectors, serializers, services
from core.exceptions import error_response

_ERROR_STATUS = {
    "forbidden": status.HTTP_403_FORBIDDEN,
}


def _service_error(exc: services.WorkoutsServiceError) -> Response:
    return error_response(_ERROR_STATUS[exc.code], code=exc.code, message=exc.message)


class WorkoutListView(generics.ListCreateAPIView):
    """Liste des plans visibles + création d'un plan pour le connecté."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.WorkoutSerializer

    def get_queryset(self):
        return (
            selectors.visible_workouts(self.request.user)
            .select_related("athlete")
            .prefetch_related("exercises__exercise")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        granted_count = queryset.exclude(owner=request.user).count()
        if granted_count:
            record_event(
                request.user,
                "workout.listed",
                None,
                metadata={"granted_workouts": granted_count},
                request=request,
            )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = serializers.CreateWorkoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            workout = services.create_workout(request.user, serializer.validated_data)
        except services.WorkoutsServiceError as exc:
            return _service_error(exc)
        output = serializers.WorkoutSerializer(workout, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class WorkoutDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail d'un plan visible + mise à jour / suppression selon les droits."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.WorkoutSerializer
    http_method_names = ["get", "patch", "delete"]  # pas de PUT : périmètre API

    def get_object(self):
        from apps.workouts.models import Workout

        workout = (
            Workout.objects.select_related("athlete")
            .prefetch_related("exercises__exercise")
            .filter(pk=self.kwargs["pk"])
            .first()
        )
        if workout is None or not selectors.can_read_workout(self.request.user, workout):
            raise exceptions.NotFound("Entraînement introuvable.")
        return workout

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.owner_id != request.user.pk:
            record_event(
                request.user,
                "workout.viewed",
                instance,
                athlete=instance.athlete,
                request=request,
            )
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.UpdateWorkoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            workout = services.update_workout(request.user, instance, serializer.validated_data)
        except services.WorkoutsServiceError as exc:
            return _service_error(exc)
        output = serializers.WorkoutSerializer(workout, context={"request": request})
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            services.delete_workout(request.user, instance)
        except services.WorkoutsServiceError as exc:
            return _service_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkoutExercisesReplaceView(generics.GenericAPIView):
    """Remplacement ordonné des exercices d'un plan (``PUT .../exercises/``).

    Le corps de la demande est ``{"exercises": [...]}`` : liste COMPLÈTE des
    lignes dans l'ordre souhaité (doublons refusés en validation, visibilité
    de chaque exercice contrôlée en service). La réponse renvoie les lignes
    réindexées 1..N.
    """

    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["put"]

    def get_object(self):
        from apps.workouts.models import Workout

        workout = (
            Workout.objects.select_related("athlete")
            .prefetch_related("exercises__exercise")
            .filter(pk=self.kwargs["pk"])
            .first()
        )
        if workout is None or not selectors.can_read_workout(self.request.user, workout):
            raise exceptions.NotFound("Entraînement introuvable.")
        return workout

    def put(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.ReplaceWorkoutExercisesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            lines = services.replace_workout_exercises(
                request.user, instance, serializer.validated_data["exercises"]
            )
        except services.WorkoutsServiceError as exc:
            return _service_error(exc)
        output = serializers.WorkoutExerciseSerializer(lines, many=True, context={"request": request})
        return Response(output.data)
