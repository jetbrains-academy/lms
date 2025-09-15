from django.conf.urls import include
from django.urls import path

from alumni import views

app_name = 'alumni'

api_urlpatterns = [
    path('list/', views.AlumniListApiView.as_view(), name='list'),
    path('promote/', views.PromoteToAlumniApiView.as_view(), name='promote'),
]

urlpatterns = [
    path('alumni/', include([
        path('', views.AlumniListView.as_view(), name='list'),
        path('promote/', views.PromoteToAlumniView.as_view(), name='promote'),
        path('consent/', views.ConsentFormView.as_view(), name='consent_form'),
    ])),
    path('api/v1/alumni/', include((api_urlpatterns, 'api'))),
]
