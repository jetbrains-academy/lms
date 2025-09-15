from django.urls import path, include
from rest_framework.routers import DefaultRouter

from staff.api import views as v

app_name = 'staff-api'

staff_router = DefaultRouter()
staff_router.register('program_runs', v.ProgramRunViewSet)

urlpatterns = [
    path('api/v1/staff/', include(staff_router.urls)),
]
