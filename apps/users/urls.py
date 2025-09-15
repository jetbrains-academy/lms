from django.conf import settings
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from learning.views import EventDetailView
from learning.views.icalendar import (
    ICalAssignmentsView, ICalClassesView, ICalEventsView
)
from users.api.views import CityViewSet, CountryViewSet
from users.views import (
    ConnectedAuthServicesView, ProfileImageUpdate, UserDetailView, UserUpdateView, StudentApplicationView,
    StudentIdUpdateView
)

api_router = DefaultRouter()
api_router.register('countries', CountryViewSet)
api_router.register('cities', CityViewSet)

user_api_patterns = [
    path('profiles/<int:student_profile_id>/set-student-id', StudentIdUpdateView.as_view(), name='student_id_update'),
    path('users/', include(api_router.urls))
]
if settings.IS_SOCIAL_ACCOUNTS_ENABLED:
    user_api_patterns += [
        path('users/<int:user>/connected-accounts/', ConnectedAuthServicesView.as_view(), name="connected_accounts"),
    ]


urlpatterns = [
    path('users/<int:pk>/', UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/profile-update-image/', ProfileImageUpdate.as_view(), name="profile_update_image"),
    path('users/students/add/<uuid:formId>', StudentApplicationView.as_view(), name='student_addition'),

    # iCalendar
    path("events/<int:pk>/", EventDetailView.as_view(), name="non_course_event_detail"),
    re_path(r'^events.ics', ICalEventsView.as_view(), name='ical_events'),
    path('users/<int:pk>/classes.ics', ICalClassesView.as_view(), name='user_ical_classes'),
    path('users/<int:pk>/assignments.ics', ICalAssignmentsView.as_view(), name='user_ical_assignments'),

    path('api/v1/', include(([
        path('', include((user_api_patterns, 'api'))),
    ])))
]
