from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout
from django import forms
from django.forms.models import ModelForm
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, FormView, UpdateView
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from alumni.permissions import ViewAlumniMenu
from alumni.serializers import AlumniUserSerializer
from alumni.services import promote_to_alumni
from api.permissions import CuratorAccessPermission
from api.views import APIBaseView
from auth.mixins import RolePermissionRequiredMixin, PermissionRequiredMixin
from core.http import HttpRequest
from core.models import AcademicProgram
from core.urls import reverse
from learning.settings import StudentStatuses
from users.api.serializers import CitySerializer
from users.mixins import CuratorOnlyMixin
from users.models import StudentProfile, User, StudentTypes, AlumniConsent, City


class AlumniListView(PermissionRequiredMixin, TemplateView):
    template_name = "lms/alumni/list.html"
    permission_required = ViewAlumniMenu.name

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        alumni_profile = request.user.get_student_profile(
            profile_type=StudentTypes.ALUMNI
        )
        if (
            alumni_profile
            and alumni_profile.alumni_consent == AlumniConsent.NOT_SET
            and not request.user.is_curator
        ):
            return HttpResponseRedirect(reverse('alumni:consent_form'))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        program_year_tuples = (
            StudentProfile.objects.filter(
                type=StudentTypes.REGULAR,
                status=StudentStatuses.GRADUATED,
            )
            .order_by(
                'academic_program_enrollment__program__title',
                'year_of_graduation',
            )
            .values_list(
                'academic_program_enrollment__program__pk',
                'academic_program_enrollment__program__title',
                'year_of_graduation',
            )
            .distinct()
        )
        programs = [
            {
                'program_id': x[0],
                'program_title': x[1],
                'graduation_year': x[2],
            }
            for x in program_year_tuples
        ]
        cities = City.objects.all()
        cities_serialized = CitySerializer(cities, many=True).data
        context.update(
            {'react_data': {'programs': programs, 'cities': cities_serialized}}
        )
        return context


class AlumniListApiView(RolePermissionRequiredMixin, APIBaseView):
    permission_classes = [ViewAlumniMenu]

    class InputSerializer(serializers.Serializer):
        program = serializers.PrimaryKeyRelatedField(
            queryset=AcademicProgram.objects.all(),
            required=False,
            allow_null=True,
        )
        graduation_year = serializers.IntegerField(
            required=False,
            allow_null=True,
        )
        city = serializers.PrimaryKeyRelatedField(
            queryset=City.objects.all(),
            required=False,
            allow_null=True,
        )

        def validate(self, data):
            if ('program' in data) ^ ('graduation_year' in data):
                raise serializers.ValidationError(
                    '"program" and "graduation_year" fields can only be set together'
                )
            return data

    class OutputSerializer(serializers.Serializer):
        alumni = AlumniUserSerializer(many=True)

    def get(self, request: Request, **kwargs) -> Response:
        serializer = self.InputSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        users = User.objects.filter(
            student_profiles__type=StudentTypes.ALUMNI,
        ).order_by('last_name', 'first_name')
        if not request.user.is_curator:
            users = users.filter(
                student_profiles__alumni_consent=AlumniConsent.ACCEPTED
            )
        if program := data.get('program'):
            users = users.filter(
                student_profiles__academic_program_enrollment__program=program,
                student_profiles__year_of_graduation=data['graduation_year'],
            )
        if city := data.get('city'):
            users = users.filter(city=city)
        return Response(self.OutputSerializer({'alumni': users}).data)


class PromoteToAlumniView(CuratorOnlyMixin, TemplateView):
    template_name = "lms/alumni/promote.html"


class PromoteToAlumniApiView(RolePermissionRequiredMixin, APIBaseView):
    permission_classes = [CuratorAccessPermission]

    class InputSerializer(serializers.Serializer):
        student_profiles = serializers.PrimaryKeyRelatedField(
            many=True, queryset=StudentProfile.objects.all()
        )

    def post(self, request: Request, **kwargs) -> Response:
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student_profiles = serializer.validated_data['student_profiles']
        for student_profile in student_profiles:
            promote_to_alumni(student_profile)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlumniConsentForm(ModelForm):
    consent = forms.BooleanField(
        label=_('I consent to share my contact information with other alumni'),
        required=False,
    )

    class Meta:
        model = StudentProfile
        fields = ('consent',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'consent',
            Submit('save', 'Save'),
        )
        self.initial['consent'] = self.instance.alumni_consent == AlumniConsent.ACCEPTED

    def save(self, commit=True):
        if self.cleaned_data['consent']:
            self.instance.alumni_consent = AlumniConsent.ACCEPTED
        else:
            self.instance.alumni_consent = AlumniConsent.DECLINED
        return super().save(commit)


class ConsentFormView(PermissionRequiredMixin, UpdateView):
    template_name = "lms/alumni/consent_form.html"
    permission_required = ViewAlumniMenu.name
    form_class = AlumniConsentForm
    alumni_profile: StudentProfile

    def setup(self, request: HttpRequest, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.alumni_profile = request.user.get_student_profile(
            profile_type=StudentTypes.ALUMNI
        )

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        if not self.alumni_profile:
            # curators have access to alumni tab, but have no alumni profile
            return HttpResponseRedirect(reverse('alumni:list'))
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.alumni_profile

    def get_success_url(self):
        return reverse('alumni:list')
