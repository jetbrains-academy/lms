from enum import Enum

import django.views.generic
from django.db.models import Prefetch
from django.views import View
from pandas import DataFrame
from vanilla import TemplateView

from auth.mixins import PermissionRequiredMixin
from core.reports import dataframe_to_response
from courses.views.mixins import CourseURLParamsMixin
from learning.models import Enrollment
from learning.permissions import ViewStudentGroup
from learning.settings import StudentStatuses
from users.models import User


class CourseStudentFacesViewMixin(PermissionRequiredMixin, CourseURLParamsMixin):
    permission_required = ViewStudentGroup.name
    users: list[User]

    def get_permission_object(self):
        return self.course

    def get_course_queryset(self):
        enrollment_qs = Enrollment.active.select_related('student').order_by(
            'student__last_name', 'student__first_name', 'student__pk'
        )
        return (
            super()
            .get_course_queryset()
            .prefetch_related(Prefetch('enrollment_set', enrollment_qs))
        )

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.users = [x.student for x in self.course.enrollment_set.all()]


class CourseStudentFacesView(CourseStudentFacesViewMixin, TemplateView):
    template_name = "lms/courses/course_student_faces.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'course': self.course,
            'users': self.users,
            'StudentStatuses': StudentStatuses,
        })
        return context


class FacesColumn(str, Enum):
    ID = 'ID'
    FIRST_NAME = 'First Name'
    LAST_NAME = 'Last Name'
    EMAIL = 'Email'
    TELEGRAM = 'Telegram'
    GITHUB = 'Github'
    CODEFORCES = 'Codeforces'
    COGNITERRA = 'Cogniterra'
    JETBRAINS = 'JetBrains account'
    LINKEDIN = 'LinkedIn'


class CourseStudentFacesCSVView(CourseStudentFacesViewMixin, View):
    def get(self, request, *args, **kwargs):
        header = [x.value for x in FacesColumn]
        rows = []
        for user in self.users:
            rows.append([
                user.id,
                user.first_name,
                user.last_name,
                user.email,
                user.telegram_username,
                user.github_login,
                user.codeforces_login,
                user.cogniterra_user_id,
                user.jetbrains_account,
                user.linkedin_profile,
            ])
        df = DataFrame.from_records(columns=header, data=rows, index='ID')
        filename = f'{self.course.meta_course.slug}_{self.course.semester.slug}_students'
        return dataframe_to_response(df, 'csv', filename)



