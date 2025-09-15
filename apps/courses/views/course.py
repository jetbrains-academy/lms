from django.apps import apps
from django.contrib.auth.views import redirect_to_login
from django.db.models import Prefetch
from django.views import generic
from vanilla import DetailView

from auth.mixins import PermissionRequiredMixin
from core.exceptions import Redirect
from core.http import AuthenticatedHttpRequest
from courses.constants import TeacherRoles
from courses.forms import CourseUpdateForm
from courses.models import Course, CourseGroupModes, CourseProgramBinding, CourseTeacher
from courses.permissions import (
    CreateAssignment, CreateCourseClass, EditCourse, ViewCourseContacts,
    ViewCourseInternalDescription, can_view_private_materials, ViewCourse, ViewAssignment
)
from courses.services import group_teachers
from courses.tabs import CourseInfoTab, TabNotFound, get_course_tab_list
from courses.views.mixins import CourseURLParamsMixin
from learning.models import CourseNewsNotification
from learning.permissions import CreateCourseNews, ViewOwnEnrollments, ViewStudentGroup, \
    EnrollOrLeavePermissionObject, ViewOwnStudentAssignment
from learning.services import course_access_role
from learning.teaching.utils import get_student_groups_url

__all__ = ('CourseDetailView', 'CourseUpdateView')


class CourseDetailView(PermissionRequiredMixin, CourseURLParamsMixin, DetailView):
    model = Course
    permission_required = ViewCourse.name
    template_name = "lms/courses/course_detail.html"
    context_object_name = 'course'
    request: AuthenticatedHttpRequest

    def get_course_queryset(self):
        teachers = Prefetch('course_teachers',
                            queryset=(CourseTeacher.objects
                                      .select_related("teacher")
                                      .order_by('teacher__last_name',
                                                'teacher__first_name')))
        return (super().get_course_queryset()
                .prefetch_related(teachers))

    def get_permission_object(self):
        return self.course

    def get_object(self):
        return self.course

    def get_context_data(self, *args, **kwargs):
        course = self.course
        # Tabs
        tab_list = get_course_tab_list(self.request, course)
        try:
            show_tab = self.kwargs.get('tab', CourseInfoTab.type)
            tab_list.set_active_tab(show_tab)
        except TabNotFound:
            raise Redirect(to=redirect_to_login(self.request.get_full_path()))
        # Teachers
        by_role = group_teachers(course.course_teachers.all())
        teachers = {'main': [], 'spectators': [], 'others': []}
        has_organizers = False
        for role, ts in by_role.items():
            if role in (TeacherRoles.LECTURER, TeacherRoles.SEMINAR, TeacherRoles.ORGANIZER):
                if role == TeacherRoles.ORGANIZER:
                    has_organizers = True
                teachers['main'].extend(ts)
            elif role != TeacherRoles.SPECTATOR:
                teachers['others'].extend(ts)
        user = self.request.user
        can_add_assignment = user.has_perm(CreateAssignment.name, course)
        can_add_course_classes = user.has_perm(CreateCourseClass.name, course)
        can_add_news = user.has_perm(CreateCourseNews.name, course)
        can_view_course_contacts = user.has_perm(ViewCourseContacts.name, course)
        can_view_course_internal_description = user.has_perm(ViewCourseInternalDescription.name, course)
        can_edit_description = user.has_perm(EditCourse.name, course)
        can_view_student_groups = user.has_perm(ViewStudentGroup.name, course)

        perm_obj = EnrollOrLeavePermissionObject(course, user.get_student_profile())
        can_enroll = user.has_perm("learning.enroll_in_course", perm_obj)
        can_leave = user.has_perm("learning.leave_course", perm_obj)
        context = {
            'CourseGroupModes': CourseGroupModes,
            'cad_add_news': can_add_news,
            'can_add_assignment': can_add_assignment,
            'can_add_course_classes': can_add_course_classes,
            'can_view_course_contacts': can_view_course_contacts,
            'can_view_course_internal_description': can_view_course_internal_description,
            'can_edit_description': can_edit_description,
            'can_view_student_groups': can_view_student_groups,
            'can_enroll': can_enroll,
            'can_leave': can_leave,
            'get_student_groups_url': get_student_groups_url,
            'course': course,
            'course_tabs': tab_list,
            'has_organizers': has_organizers,
            'teachers': teachers,
            'has_access_to_private_materials': can_view_private_materials(user, course),
            'ViewAssignment': ViewAssignment,
            'ViewOwnStudentAssignment': ViewOwnStudentAssignment,
            **self._get_additional_context(course)
        }
        return context

    def _get_additional_context(self, course, **kwargs):
        request_user = self.request.user
        tz_override = request_user.time_zone
        if request_user.has_perm(ViewOwnEnrollments.name):
            request_user_enrollment = request_user.get_enrollment(course.pk)
        else:
            request_user_enrollment = None
        # Attach unread notifications count if authenticated user is in
        # a mailing list
        unread_news = None
        is_actual_teacher = course.is_actual_teacher(request_user.pk)
        if request_user_enrollment or is_actual_teacher:
            unread_news = (CourseNewsNotification.unread
                           .filter(course_offering_news__course=course,
                                   user=request_user)
                           .count())
        return {
            'tz_override': tz_override,
            'request_user_enrollment': request_user_enrollment,
            'is_actual_teacher': is_actual_teacher,
            'unread_news': unread_news,
        }


class CourseUpdateView(PermissionRequiredMixin, CourseURLParamsMixin,
                       generic.UpdateView):
    model = Course
    template_name = "courses/simple_crispy_form.html"
    permission_required = EditCourse.name
    form_class = CourseUpdateForm

    def get_object(self, queryset=None):
        return self.course

    def get_permission_object(self):
        return self.course

    def get_initial(self):
        """Keep in mind that `initial` overrides values from model dict"""
        initial = super().get_initial()
        # Note: In edit view we always have an object
        if not self.object.description:
            initial["description"] = self.object.meta_course.description
        return initial

