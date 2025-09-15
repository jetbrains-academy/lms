from collections import OrderedDict
from itertools import groupby

from django.contrib.auth.views import redirect_to_login
from django.db.models import Prefetch, Q
from django.http import HttpResponseRedirect
from django.utils.translation import pgettext_lazy
from django.views import View
from django_filters.views import FilterMixin
from rest_framework.renderers import JSONRenderer
from vanilla import TemplateView

from courses.models import CourseProgramBinding
from core.exceptions import Redirect
from core.urls import reverse
from courses.constants import SemesterTypes
from courses.models import Course, CourseTeacher
from courses.selectors import course_teachers_prefetch_queryset
from courses.utils import TermPair, get_current_term_pair
from learning.models import Enrollment
from lms.api.serializers import OfferingsCourseSerializer
from lms.filters import CoursesAtAcademicProgram
from lms.utils import PublicRoute, PublicRouteException, group_terms_by_academic_year
from users.models import StudentTypes


class IndexView(View):
    def get(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            redirect_to = reverse('auth:login')
        else:
            redirect_to = user.get_absolute_url()
        if user.is_curator:
            redirect_to = reverse('staff:student_search')
        elif user.is_teacher:
            redirect_to = reverse('teaching:assignments_check_queue')
        elif user.is_student:
            redirect_to = reverse('study:assignment_list')
        return HttpResponseRedirect(redirect_to=redirect_to)


class CourseOfferingsView(FilterMixin, TemplateView):
    filterset_class = CoursesAtAcademicProgram
    template_name = "lms/course_offerings.html"

    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        course_teachers = Prefetch('course_teachers',
                                   queryset=course_teachers_prefetch_queryset(
                                       hidden_roles=(CourseTeacher.roles.spectator,)
                                   ))

        courses = Course.objects
        student_profile = user.get_student_profile()
        if not user.is_curator and not user.is_teacher:
            if student_profile is None:
                courses = courses.none()
            elif student_profile.type == StudentTypes.INVITED:
                student_enrollments = (Enrollment.active
                                       .filter(student_id=user)
                                       .select_related("course")
                                       .only('id', 'course_id'))
                student_enrollments = {e.course_id: e for e in student_enrollments}
                courses_pk = [ci.course_id for ci in (CourseProgramBinding
                                                      .objects
                                                      .student_can_enroll_by_invitation(student_profile)
                                                      .only('course_id'))]
                enrolled_in = Q(id__in=list(student_enrollments))
                has_invitation = Q(id__in=courses_pk)
                courses = courses.filter(enrolled_in | has_invitation)
            elif student_profile.type == StudentTypes.REGULAR and student_profile.academic_program_enrollment:
                courses = courses.in_program(student_profile.academic_program_enrollment.program.code)
        return (courses
                .exclude(semester__type=SemesterTypes.SUMMER)
                .select_related('meta_course', 'semester')
                .only("pk",
                      "meta_course__name", "meta_course__slug",
                      "semester__year", "semester__index", "semester__type")
                .prefetch_related(course_teachers)
                .order_by('-semester__year', '-semester__index',
                          'meta_course__name'))

    def get_context_data(self, **kwargs):
        filterset_class = self.get_filterset_class()
        filterset = self.get_filterset(filterset_class)
        if not filterset.is_valid():
            raise Redirect(to=reverse("course_list"))
        term_options = {
            SemesterTypes.AUTUMN: pgettext_lazy("adjective", "autumn"),
            SemesterTypes.SPRING: pgettext_lazy("adjective", "spring"),
        }
        courses_qs = filterset.qs
        terms = group_terms_by_academic_year(courses_qs)
        active_academic_year, active_type = self.get_term(filterset, courses_qs)
        if active_type == SemesterTypes.SPRING:
            active_year = active_academic_year + 1
        else:
            active_year = active_academic_year
        active_slug = "{}-{}".format(active_year, active_type)
        # Group courses by (year, term_type)
        courses = OrderedDict()
        for term, cs in groupby(courses_qs, key=lambda x: x.semester):
            courses[term.slug] = OfferingsCourseSerializer(cs, many=True).data
        context = {
            "TERM_TYPES": term_options,
            "terms": terms,
            "courses": courses,
            "active_academic_year": active_academic_year,
            "active_type": active_type,
            "active_slug": active_slug,
            "json": JSONRenderer().render({
                "initialFilterState": {
                    "academicYear": active_academic_year,
                    "selectedTerm": active_type,
                    "termSlug": active_slug
                },
                "terms": terms,
                "termOptions": term_options,
                "courses": courses
            }).decode('utf-8'),
        }
        return context

    def get_term(self, filters, courses):
        # Not sure this is the best place for this method
        assert filters.is_valid()
        if "semester" in filters.data:
            valid_slug = filters.data["semester"]
            term_year, term_type = valid_slug.split("-")
            term_year = int(term_year)
        else:
            # By default, return academic year and term type for the latest
            # available course.
            if courses:
                # Note: may hit db if `filters.qs` is not cached
                term = courses[0].semester
                term_year = term.year
                term_type = term.type
            else:
                term_pair = get_current_term_pair()
                term_year = term_pair.year
                term_type = term_pair.type
        term_pair = TermPair(term_year, term_type)
        return term_pair.academic_year, term_type
