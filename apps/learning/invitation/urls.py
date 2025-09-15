from django.conf.urls import include
from django.urls import path

from . import views as v

urlpatterns = [
    path("invitation/", include([
        path('<str:token>/', v.InvitationView.as_view(), name="invitation"),
        # TODO: email confirmation
    ])),
]
