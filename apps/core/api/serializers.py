from rest_framework import serializers

from api.utils import DynamicFieldsModelSerializer
from core.models import AcademicProgramRun
from users.models import StudentProfile


class AcademicProgramRunSerializer(DynamicFieldsModelSerializer):
    title = serializers.CharField(source='program.title')
    code = serializers.CharField(source='program.code')
    student_profiles = serializers.SerializerMethodField()

    def get_student_profiles(self, obj: AcademicProgramRun):
        from learning.api.serializers import StudentProfileSerializer
        student_profiles = StudentProfile.objects.filter(academic_program_enrollment=obj).select_related('user').all()
        return StudentProfileSerializer(student_profiles, many=True).data

    class Meta:
        model = AcademicProgramRun
        fields = ('id', 'title', 'code', 'start_year', 'student_profiles')
