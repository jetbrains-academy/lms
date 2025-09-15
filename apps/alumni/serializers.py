from rest_framework.fields import IntegerField, SerializerMethodField, CharField
from rest_framework.serializers import ModelSerializer

from learning.settings import StudentStatuses
from users.api.serializers import PhotoSerializerField, CitySerializer
from users.models import User, StudentProfile


class StudentProfileToGraduationSerializer(ModelSerializer):
    program_id = IntegerField(source='academic_program_enrollment.program.pk')
    program_title = CharField(source='academic_program_enrollment.program.title')
    graduation_year = IntegerField(source='year_of_graduation')

    class Meta:
        model = StudentProfile
        fields = ('program_id', 'program_title', 'graduation_year')


class AlumniUserSerializer(ModelSerializer):
    photo = PhotoSerializerField(User.ThumbnailSize.BASE)
    graduations = SerializerMethodField()
    city = CitySerializer()

    class Meta:
        model = User
        fields = (
            'id',
            'first_name',
            'last_name',
            'gender',
            'username',
            'email',
            'photo',
            'telegram_username',
            'graduations',
            'city',
        )

    def get_graduations(self, user: User):
        profiles = StudentProfile.objects.filter(
            user=user, status=StudentStatuses.GRADUATED
        ).all()
        return StudentProfileToGraduationSerializer(profiles, many=True).data
