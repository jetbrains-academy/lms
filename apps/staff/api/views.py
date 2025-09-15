from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from api.permissions import CuratorAccessPermission
from auth.mixins import RolePermissionRequiredMixin
from core.api.serializers import AcademicProgramRunSerializer
from core.models import AcademicProgramRun
from learning.api.serializers import StudentProfileSerializer
from users.filters import StudentFilter
from users.models import StudentProfile


class StudentOffsetPagination(LimitOffsetPagination):
    default_limit = 500


class StudentSearchJSONView(ListAPIView):
    permission_classes = [CuratorAccessPermission]
    pagination_class = StudentOffsetPagination
    filter_backends = (DjangoFilterBackend,)
    filterset_class = StudentFilter

    class OutputSerializer(StudentProfileSerializer):
        class Meta(StudentProfileSerializer.Meta):
            fields = ('pk', 'short_name', 'user_id')

    def get_serializer_class(self):
        return self.OutputSerializer

    def get_queryset(self):
        return (
            StudentProfile.objects
            .select_related('user')
            .only('user__username', 'user__first_name', 'user__last_name', 'user_id')
            .order_by('user__last_name', 'user__first_name', 'user_id')
        )


class ProgramRunViewSet(RolePermissionRequiredMixin, ViewSet):
    permission_classes = [CuratorAccessPermission]
    queryset = AcademicProgramRun.objects.all()

    def list(self, request: Request) -> Response:
        serializer = AcademicProgramRunSerializer(
            self.queryset, many=True, fields=('id', 'title', 'code', 'start_year')
        )
        return Response(serializer.data)

    def retrieve(self, request: Request, pk=None) -> Response:
        program_run = get_object_or_404(self.queryset, pk=pk)
        serializer = AcademicProgramRunSerializer(program_run)
        return Response(serializer.data)
