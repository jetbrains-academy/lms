
from vanilla import FormView

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from courses.models import CourseProgramBinding
from auth.mixins import PermissionRequiredMixin
from core.exceptions import Redirect
from core.http import HttpRequest
from core.urls import reverse
from courses.views.mixins import CourseURLParamsMixin
from learning.forms import CourseEnrollmentForm, CourseUnenrollmentForm
from learning.models import Enrollment
from learning.permissions import EnrollInCourse, EnrollOrLeavePermissionObject
from learning.services import EnrollmentService
from learning.services.enrollment_service import AlreadyEnrolled, CourseCapacityFull
from learning.services.student_group_service import (
    StudentGroupError, StudentGroupService
)


class CourseEnrollView(CourseURLParamsMixin, PermissionRequiredMixin, FormView):
    template_name = "learning/enrollment/enrollment_enter_leave.html"
    permission_required = EnrollInCourse.name

    def setup(self, request: HttpRequest, **kwargs):
        super().setup(request, **kwargs)
        self.student_profile = self.request.user.get_student_profile()
        course_invitation_binding = (
            CourseProgramBinding.objects
            .filter(course=self.course)
            .student_can_enroll_by_invitation(self.student_profile)
            .first()
        )
        if course_invitation_binding:
            self.invitation = course_invitation_binding.invitation
        else:
            self.invitation = None

    def get_form(self, data=None, files=None, **kwargs):
        return CourseEnrollmentForm(
            ask_reason=self.course.ask_enrollment_reason,
            data=data,
            files=files,
            **kwargs
        )

    def get_permission_object(self):
        return EnrollOrLeavePermissionObject(self.course, self.student_profile)

    def has_permission(self):
        has_perm = super().has_permission()
        # FIXME: remove?
        if not has_perm and not self.course.places_left:
            msg = _("No places available, sorry")
            messages.error(self.request, msg, extra_tags='timeout')
            raise Redirect(to=self.course.get_absolute_url())
        return has_perm

    def form_valid(self, form):
        reason_entry = form.cleaned_data["reason"].strip()
        student_profile = self.student_profile
        try:
            student_group = StudentGroupService.resolve(self.course,
                                                        student_profile=student_profile)
        except StudentGroupError as e:
            messages.error(self.request, str(e), extra_tags='timeout')
            raise Redirect(to=self.course.get_absolute_url())
        try:
            EnrollmentService.enroll(student_profile, self.course,
                                     reason_entry=reason_entry,
                                     student_group=student_group,
                                     invitation=self.invitation)
            msg = _("You are successfully enrolled in the course")
            messages.success(self.request, msg, extra_tags='timeout')
        except AlreadyEnrolled:
            msg = _("You are already enrolled in the course")
            messages.warning(self.request, msg, extra_tags='timeout')
        except CourseCapacityFull:
            msg = _("No places available, sorry")
            messages.error(self.request, msg, extra_tags='timeout')
            raise Redirect(to=self.course.get_absolute_url())
        if self.request.POST.get('back') == 'study:course_list':
            return_to = reverse('study:course_list')
        else:
            return_to = self.course.get_absolute_url()
        return HttpResponseRedirect(return_to)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = self.course
        return context


class CourseUnenrollView(PermissionRequiredMixin, CourseURLParamsMixin, FormView):
    template_name = "learning/enrollment/enrollment_enter_leave.html"
    permission_required = 'learning.leave_course'

    def get_form(self, data=None, files=None, **kwargs):
        return CourseUnenrollmentForm(
            ask_reason=self.course.ask_enrollment_reason,
            data=data,
            files=files,
            **kwargs
        )

    def get_permission_object(self):
        student_profile = self.request.user.get_student_profile()
        return EnrollOrLeavePermissionObject(self.course, student_profile)

    def form_valid(self, form):
        enrollment = get_object_or_404(
            Enrollment.active
            .filter(student=self.request.user, course_id=self.course.pk)
            .select_related('course', 'course__semester')
        )
        reason_leave = form.cleaned_data["reason"].strip()
        EnrollmentService.leave(enrollment, reason_leave=reason_leave)
        if self.request.GET.get('back') == 'study:course_list':
            redirect_to = reverse('study:course_list')
        else:
            redirect_to = enrollment.course.get_absolute_url()
        return HttpResponseRedirect(redirect_to)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['course'] = self.course
        return context
