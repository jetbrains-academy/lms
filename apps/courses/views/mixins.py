import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404

from core.exceptions import Redirect
from core.urls import reverse
from courses.models import Course

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from django.views import View
    CourseURLParamsMixinBase = View
else:
    CourseURLParamsMixinBase = object


class CourseURLParamsMixin(CourseURLParamsMixinBase):
    """
    This mixin helps to get course by url parameters and assigns it to the
    `course` attribute of the view instance.
    Returns 404 if course is not found or friendly part of the URL is not valid.

    Note:
        Previously friendly URL prefix was used to retrieve course record,
        now `settings.RE_COURSE_URI` contains course PK to avoid url collisions.
    """
    course: Course

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.course: Course = get_object_or_404(
            self.get_course_queryset()
                .filter(pk=kwargs['course_id'],
                        meta_course__slug=kwargs['course_slug'],
                        semester__type=kwargs['semester_type'],
                        semester__year=kwargs['semester_year'])
                .order_by('pk')
        )

    def get_course_queryset(self):
        """Returns base queryset for the course"""
        return (Course.objects
                .select_related('meta_course', 'semester'))


