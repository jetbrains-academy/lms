import json
import os
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views import generic
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django_recaptcha.client import submit
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from typing import Any, Optional

from api.views import APIBaseView
from auth.mixins import RolePermissionRequiredMixin, PermissionRequiredMixin
from auth.models import ConnectedAuthService
from auth.services import get_available_service_providers, get_connected_accounts
from core.http import AuthenticatedHttpRequest, HttpRequest
from core.models import AcademicProgramRun
from core.timezone.utils import get_gmt
from core.views import ProtectedFormMixin
from courses.models import CourseTeacher, Semester, Course
from files.handlers import MemoryImageUploadHandler, TemporaryImageUploadHandler
from learning.icalendar import get_icalendar_links
from learning.models import Enrollment, StudentAssignment
from learning.settings import StudentStatuses
from users.thumbnails import CropboxData, get_user_thumbnail, photo_thumbnail_cropbox
from .constants import Roles
from .forms import UserProfileForm, StudentCreationForm, StudentEnrollmentForm
from .models import User, StudentProfile, SubmissionForm
from .permissions import (
    ViewAccountConnectedServiceProvider, UpdateStudentProfileStudentId, ViewProfile
)
from .services import get_student_profiles, assign_role


class StudentApplicationView(generic.FormView):
    template_name = 'users/student_application.html'
    submission_form: SubmissionForm

    def dispatch(self, request, *args, **kwargs):
        self.submission_form = get_object_or_404(SubmissionForm, pk=self.kwargs['formId'])
        if (user := self.request.user).is_authenticated:
            already_enrolled = StudentProfile.objects.filter(
                user=user,
                academic_program_enrollment=self.submission_form.academic_program_run,
            ).exists()
            if already_enrolled:
                self.user = user
                return HttpResponseRedirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        if self.request.user.is_authenticated:
            return StudentEnrollmentForm
        else:
            return StudentCreationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['require_student_id'] = self.submission_form.require_student_id
        return kwargs

    def get_context_data(self, **kwargs):
        kwargs['program_run'] = self.submission_form.academic_program_run
        return super().get_context_data(**kwargs)

    def get_success_url(self):
        return self.user.get_update_profile_url()

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            user = self.request.user
        else:
            user = form.save()
        self.user = user
        program_run = self.submission_form.academic_program_run
        assign_role(account=user, role=Roles.STUDENT)
        profile = StudentProfile(
            user=user,
            academic_program_enrollment_id=program_run.pk,
            year_of_admission=program_run.start_year,
            type='regular',
            student_id=form.cleaned_data['student_id'].strip()
        )
        profile.save()
        return super().form_valid(form)


class UserDetailView(PermissionRequiredMixin, generic.TemplateView):
    template_name = "lms/user_profile/user_detail.html"
    permission_required = ViewProfile.name

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.user = get_object_or_404(
            self.get_queryset()
            .filter(pk=kwargs['pk'])
        )

    def get_permission_object(self):
        return self.user

    def get_queryset(self, *args, **kwargs):
        enrollments_queryset = (Enrollment.active
                                .select_related('course',
                                                'course__semester',
                                                'course__meta_course')
                                .order_by("course"))
        teaching_queryset = (
            Course.objects
            .filter(~CourseTeacher.has_any_hidden_role(lookup='course_teachers__roles'))
            .select_related('semester', 'meta_course')
        )
        prefetch_list = [
            Prefetch('teaching_set', queryset=teaching_queryset),
            Prefetch('enrollment_set', queryset=enrollments_queryset)
        ]
        filters = {}
        if not self.request.user.is_curator:
            filters["is_active"] = True
        return (auth.get_user_model()._default_manager
                .filter(**filters)
                .prefetch_related(*prefetch_list)
                .distinct('pk'))

    def get_context_data(self, **kwargs):
        u = self.request.user
        profile_user = self.user
        is_certificates_of_participation_enabled = False
        is_social_accounts_enabled = settings.IS_SOCIAL_ACCOUNTS_ENABLED
        can_edit_profile = (u == profile_user or u.is_curator)
        can_view_personal_data = (u == profile_user or u.is_curator)
        can_view_assignments = u.is_curator
        icalendars = []
        if profile_user.pk == u.pk:
            icalendars = get_icalendar_links(profile_user,
                                             url_builder=self.request.build_absolute_uri)
        current_semester = Semester.get_current()
        if profile_user.time_zone is not None:
            time_zone = f"{get_gmt(profile_user.time_zone)} {profile_user.time_zone}"
        else:
            time_zone = "Unknown"
        context = {
            "StudentStatuses": StudentStatuses,
            "profile_user": profile_user,
            "time_zone": time_zone,
            "icalendars": icalendars,
            "is_certificates_of_participation_enabled": is_certificates_of_participation_enabled,
            "can_edit_profile": can_edit_profile,
            "current_semester": current_semester,
            "can_view_personal_data": can_view_personal_data,
            "can_view_assignments": can_view_assignments,
        }
        context['available_providers'] = (is_social_accounts_enabled and
                                          can_edit_profile and
                                          get_available_service_providers())
        if can_view_assignments:
            assignments_qs = (StudentAssignment.objects
                              .for_student(profile_user)
                              .in_term(current_semester)
                              .order_by('assignment__course__meta_course__name',
                                        'assignment__deadline_at',
                                        'assignment__title'))
            context['personal_assignments'] = assignments_qs.all()
        js_app_data = {"props": {}}
        photo_data = {}
        if can_edit_profile:
            photo_data = {
                "userID": profile_user.pk,
                "photo": profile_user.photo_data
            }
        js_app_data["props"]["photo"] = json.dumps(photo_data)
        js_app_data["props"]["socialAccounts"] = json.dumps({
            "isEnabled": is_social_accounts_enabled and can_edit_profile,
            "userID": profile_user.pk,
        })
        context["appData"] = js_app_data
        # Collect stats about successfully passed courses
        if u.is_curator:
            # TODO: add derivable classes_total field to Course model
            queryset = (profile_user.enrollment_set(manager='active')
                        .annotate(classes_total=Count('course__courseclass')))
            context['stats'] = profile_user.stats(current_semester,
                                                  enrollments=queryset)
        if can_view_personal_data:
            context['enrollments'] = profile_user.enrollment_set.all()

            student_profiles = get_student_profiles(user=profile_user,
                                                    fetch_status_history=True)
            # Aggregate stats needed for student profiles
            passed_courses = set()
            in_current_term = set()
            for enrollment in profile_user.enrollment_set.all():
                grading_system = enrollment.course_program_binding.grading_system
                if enrollment.grade >= grading_system.pass_from:
                    passed_courses.add(enrollment.course.meta_course_id)
                if enrollment.course.semester_id == current_semester.pk:
                    in_current_term.add(enrollment.course.meta_course_id)
            context['student_profiles'] = student_profiles
            context['syllabus_legend'] = {
                'passed_courses': passed_courses,
                'in_current_term': in_current_term
            }
            if student_profiles:
                main_profile = student_profiles[0]  # because of profile ordering
                context['academic_disciplines'] = ", ".join(d.name for d in main_profile.academic_disciplines.all())
                if main_profile.invitation:
                    context['invitation'] = main_profile.invitation
        return context


class UserUpdateView(ProtectedFormMixin, generic.UpdateView):
    model = User
    template_name = "lms/user_profile/user_edit.html"
    form_class = UserProfileForm

    def get_form_kwargs(self):
        kwargs = super(UserUpdateView, self).get_form_kwargs()
        kwargs.update({'editor': self.request.user,
                       'student': self.object})
        return kwargs

    def is_form_allowed(self, user, obj):
        return obj.pk == user.pk or user.is_curator

    def form_valid(self, form):
        """If the form is valid, save the associated model."""
        with transaction.atomic():
            self.object = form.save()
        return super().form_valid(form)


class ConnectedAuthServicesView(RolePermissionRequiredMixin, APIBaseView):
    permission_classes = [ViewAccountConnectedServiceProvider]
    request: AuthenticatedHttpRequest
    account: User

    class InputSerializer(serializers.Serializer):
        user = serializers.IntegerField()

    class OutputSerializer(serializers.ModelSerializer):
        login = serializers.SerializerMethodField()

        class Meta:
            model = ConnectedAuthService
            fields = ('provider', 'uid', 'login')

        def get_login(self, obj: ConnectedAuthService) -> Optional[str]:
            return obj.login

    def setup(self, request: HttpRequest, **kwargs: Any) -> None:
        super().setup(request, **kwargs)
        serializer = self.InputSerializer(data=kwargs)
        serializer.is_valid(raise_exception=True)
        queryset = (User.objects
                    .filter(pk=serializer.validated_data['user']))
        self.account = get_object_or_404(queryset)

    def get_permission_object(self) -> User:
        return self.account

    def get(self, request: AuthenticatedHttpRequest, **kwargs) -> Response:
        connected_accounts = get_connected_accounts(user=self.account)
        data = self.OutputSerializer(connected_accounts, many=True).data
        return Response(status=status.HTTP_200_OK, data={
            "edges": data
        })


class ProfileImageUpdate(generic.base.View):
    """
    This view saves new profile image or updates preview dimensions
    (cropbox data) for the already uploaded image.
    """

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        """
        Upload handlers will be triggered by accessing `request.POST` or
        `request.FILES`. `CsrfViewMiddleware` internally use `request.POST`
        but only if protection is enabled. So workaround is:
            * delay CSRF protection using `csrf_exempt` decorator
            * modify upload handlers of the request object
            * enable CSRF-protection for the view with `csrf_protect` decorator
        """
        request.upload_handlers = [MemoryImageUploadHandler(request),
                                   TemporaryImageUploadHandler(request)]
        return self._dispatch(request, *args, **kwargs)

    @method_decorator(csrf_protect)
    def _dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseBadRequest("Bad User")

        user_id = kwargs['pk']
        if user_id != request.user.id and not request.user.is_curator:
            return HttpResponseForbidden()

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return HttpResponseBadRequest("User not found")

        if "crop_data" in request.POST:
            return self._update_cropbox(request, user)
        else:
            return self._update_image(request, user)

    @staticmethod
    def _update_cropbox(request, user):
        crop_data_form = CropboxData(data=request.POST)
        if not crop_data_form.is_valid():
            return JsonResponse({
                "success": False,
                "reason": "Invalid cropbox data"
            })
        crop_data_str = photo_thumbnail_cropbox(crop_data_form.to_json())
        thumbnail = get_user_thumbnail(user, User.ThumbnailSize.BASE,
                                       crop='center', use_stub=False,
                                       cropbox=crop_data_str)
        if thumbnail:
            user.cropbox_data = crop_data_form.to_json()
            user.save(update_fields=['cropbox_data'])
            ret_json = {"success": True, "thumbnail": thumbnail.url}
        else:
            ret_json = {"success": False, "reason": "Thumbnail generation error"}
        return JsonResponse(ret_json)

    def _update_image(self, request, user):
        if len(request.FILES) > 1:
            return HttpResponseBadRequest("Multi upload is not supported")
        elif len(request.FILES) != 1:
            return HttpResponseBadRequest("Bad file format or size")

        image_file = list(request.FILES.values())[0]
        user.photo = image_file
        user.cropbox_data = {}
        user.save(update_fields=['photo', 'cropbox_data'])
        image_url = user.photo.url

        # TODO: generate default crop settings and return them
        payload = {
            'success': True,
            "url": image_url,
            'filename': os.path.basename(user.photo.name)
        }
        return JsonResponse(payload)


class StudentIdUpdateView(RolePermissionRequiredMixin, APIBaseView):
    permission_classes = [UpdateStudentProfileStudentId]
    profile: StudentProfile

    def setup(self, request: HttpRequest, **kwargs) -> None:
        super().setup(request, **kwargs)
        self.profile = get_object_or_404(
            StudentProfile.objects
            .filter(pk=kwargs['student_profile_id'])
        )

    def get_permission_object(self) -> StudentProfile:
        return self.profile

    class InputSerializer(serializers.Serializer):
        student_id = serializers.CharField()

    def post(self, request: Request, **kwargs) -> Response:
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.profile.student_id = serializer.validated_data['student_id']
        self.profile.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
