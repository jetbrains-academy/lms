from django.conf.urls import include
from django.urls import path, re_path

from courses.urls import RE_COURSE_URI
from learning.study.views import ProgramsView

from .views import (
    CourseEnrollView, CourseNewsNotificationUpdate, CourseStudentsView,
    CourseUnenrollView
)

urlpatterns = [
    path("courses/", include([
        re_path(RE_COURSE_URI, include([
            path("enroll/", CourseEnrollView.as_view(), name="course_enroll"),
            path("unenroll/", CourseUnenrollView.as_view(), name="course_leave"),
            path("students/", CourseStudentsView.as_view(), name="course_students"),
            path("news/notifications/", CourseNewsNotificationUpdate.as_view(), name="course_news_notifications_read"),
        ])),
    ])),


    path('teaching/', include('learning.teaching.urls')),

    path('learning/', include('learning.study.urls')),
    path('learning/programs/', ProgramsView.as_view(), name='programs'),
]
