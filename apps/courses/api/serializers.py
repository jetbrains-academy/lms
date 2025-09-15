from rest_framework import serializers

from core.utils import render_markdown_and_cache
from courses.models import Assignment, Course, CourseTeacher, Semester


class SemesterSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="pk")
    # name = serializers.SerializerMethodField()

    class Meta:
        model = Semester
        fields = ("id", "index", "year", "academic_year", "type")

    def get_name(self, obj: Semester):
        return str(obj)


class CourseTeacherSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="teacher_id")
    name = serializers.CharField(source='teacher.get_abbreviated_name')

    class Meta:
        model = CourseTeacher
        fields = ("id", "name",)


class CourseSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    semester = SemesterSerializer()
    teachers = CourseTeacherSerializer(source="course_teachers",
                                       many=True, read_only=True)

    class Meta:
        model = Course
        fields = ('id', 'name', 'url', 'semester', 'teachers')

    def get_name(self, obj: Course):
        return obj.meta_course.name

    def get_url(self, obj: Course):
        return obj.get_absolute_url()


class BaseAssignmentSerializer(serializers.ModelSerializer):
    text = serializers.SerializerMethodField()
    solution_format = serializers.CharField(source='submission_type')

    class Meta:
        model = Assignment
        fields = ('pk', 'deadline_at', 'title', 'text', 'ttc',
                  'maximum_score', 'weight', 'solution_format')

    def get_text(self, obj: Assignment):
        return render_markdown_and_cache(obj.text, "assignment_text", 3600,
                                         obj.pk, obj.modified)
