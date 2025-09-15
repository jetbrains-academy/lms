from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views import generic

from users.forms import StudentCreationForm, StudentEnrollmentForm
from core.urls import reverse
from courses.utils import date_to_term_pair, get_current_term_pair
from learning.models import Invitation
from users.models import StudentProfile, StudentTypes, User
from users.services import create_student_profile


def is_student_profile_valid(user: User) -> bool:
    student_profile = user.get_student_profile()
    if not student_profile or not student_profile.is_active:
        return False
    if student_profile.type == StudentTypes.INVITED:
        created_on_term = date_to_term_pair(student_profile.created)
        if created_on_term != get_current_term_pair():
            return False
    return bool(user.first_name and user.last_name)


def create_invited_profile(user: User, invitation: Invitation) -> StudentProfile:
    return create_student_profile(
        user=user,
        profile_type=StudentTypes.INVITED,
        year_of_admission=invitation.semester.academic_year,
        invitation=invitation,
    )


class InvitationView(generic.FormView):
    template_name = 'learning/invitation/enroll.html'
    invitation: Invitation

    def dispatch(self, request, *args, **kwargs):
        self.invitation = get_object_or_404(Invitation, token=kwargs['token'])

        if request.user.is_authenticated:
            already_enrolled = self.invitation.enrolled_students.filter(user_id=request.user.id).exists()
            if already_enrolled:
                return HttpResponseRedirect(self.get_success_url())

        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        if self.request.user.is_authenticated:
            return StudentEnrollmentForm
        else:
            return StudentCreationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['require_student_id'] = False
        return kwargs

    def get_context_data(self, **kwargs):
        kwargs['invitation'] = self.invitation
        return super().get_context_data(**kwargs)

    def get_success_url(self):
        return reverse('study:course_list')

    def form_valid(self, form):
        if self.request.user.is_authenticated:
            user = self.request.user
        else:
            user = form.save()

        if is_student_profile_valid(self.request.user):
            profile = self.request.user.get_student_profile()
        else:
            profile = create_invited_profile(user, self.invitation)
        self.invitation.enrolled_students.add(profile)
        return super().form_valid(form)
