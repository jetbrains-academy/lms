from django.urls import include, path, re_path, register_converter

from courses.urls import RE_COURSE_URI
from learning.gradebook.views import (
    GradeBookCSVView,
    GradeBookView,
    ImportAssignmentScoresByEnrollmentIDView,
    ImportCourseGradesByEnrollmentIDView
)
from staff.api.views import StudentSearchJSONView
from staff.views import (
    CourseParticipantsIntersectionView,
    EnrollmentInvitationListView, ExportsView,
    GradeBookListView,
    HintListView, InvitationStudentsProgressReportView,
    ProgressReportForSemesterView, ProgressReportFullView, StudentFacesView,
    StudentSearchCSVView, StudentSearchView
)

app_name = 'staff'


class SupportedExportFormatConverter:
    regex = 'csv|xlsx'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(SupportedExportFormatConverter, 'export_fmt')


urlpatterns = [
    path('staff/', include([
        path('gradebooks/', include([
            path('', GradeBookListView.as_view(), name='gradebook_list'),
            re_path(RE_COURSE_URI, include([
                path('', GradeBookView.as_view(is_for_staff=True, permission_required="teaching.view_gradebook"), name='gradebook'),
                path('csv/', GradeBookCSVView.as_view(permission_required="teaching.view_gradebook"), name='gradebook_csv'),
            ])),
            path('<int:course_id>/import/', include([
                path('assignments-enrollments', ImportAssignmentScoresByEnrollmentIDView.as_view(), name='gradebook_import_scores_by_enrollment_id'),
                path('course-grades-enrollments', ImportCourseGradesByEnrollmentIDView.as_view(), name='gradebook_import_course_grades_by_enrollment_id')
            ])),
        ])),

        path('student-search/', StudentSearchView.as_view(), name='student_search'),
        path('student-search.json', StudentSearchJSONView.as_view(), name='student_search_json'),
        # Note: CSV view doesn't use pagination
        path('student-search.csv', StudentSearchCSVView.as_view(), name='student_search_csv'),


        path('faces/', StudentFacesView.as_view(), name='student_faces'),

        path('course-participants/', CourseParticipantsIntersectionView.as_view(), name='course_participants_intersection'),


        path('exports/', ExportsView.as_view(), name='exports'),

        path('reports/enrollment-invitations/', include([
            path('', EnrollmentInvitationListView.as_view(), name='enrollment_invitations_list'),
            re_path(r'^(?P<invitation_id>\d+)/(?P<output_format>csv|xlsx)/$', InvitationStudentsProgressReportView.as_view(), name='students_progress_report_for_invitation'),
        ])),
        path('reports/students-progress/', include([
            re_path(r'^(?P<output_format>csv|xlsx)/(?P<on_duplicate>max|last)/$', ProgressReportFullView.as_view(), name='students_progress_report'),
            re_path(r'^terms/(?P<term_year>\d+)/(?P<term_type>\w+)/(?P<output_format>csv|xlsx)/$', ProgressReportForSemesterView.as_view(), name='students_progress_report_for_term'),
        ])),


        path('warehouse/', HintListView.as_view(), name='staff_warehouse'),
    ])),

    path('', include('staff.api.urls')),
]


