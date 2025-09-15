import re

from django.core.exceptions import ValidationError
from django.forms import SlugField, forms
from django.http import QueryDict
from django_filters import Filter, FilterSet

from courses.constants import SemesterTypes
from courses.models import Course


class SlugFilter(Filter):
    field_class = SlugField


class SemesterFilter(SlugFilter):
    def filter(self, qs, value):
        return qs


_term_types = r"|".join(slug for slug, _ in SemesterTypes.choices)
semester_slug_re = re.compile(r"^(?P<term_year>\d{4})-(?P<term_type>" + _term_types + r")$")


class CoursesFilterForm(forms.Form):
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('semester'):
            semester_value = cleaned_data['semester']
            match = semester_slug_re.search(semester_value)
            if not match:
                msg = "Incorrect term slug format"
                raise ValidationError(msg)
            term_type = match.group("term_type")
            # More strict rules for term types
            if term_type not in [SemesterTypes.AUTUMN, SemesterTypes.SPRING]:
                raise ValidationError("Supported term types: [autumn, spring]")
        return cleaned_data


class CoursesAtAcademicProgram(FilterSet):
    semester = SemesterFilter()

    class Meta:
        model = Course
        form = CoursesFilterForm
        fields = ['semester']

    def __init__(self, data=None, queryset=None, request=None, **kwargs):
        if data is not None:
            data = data.copy()  # get a mutable copy of the QueryDict
        else:
            data = QueryDict(mutable=True)
        super().__init__(data=data, queryset=queryset, request=request, **kwargs)


class CoursesFilter(FilterSet):
    """
    Returns courses available in a target branch.
    """
    # FIXME: мб сначала валидировать request данные? зачем смешивать с фильтрацией? Тогда отсюда можно удалить semester, т.к. он не к месту
    semester = SemesterFilter()

    class Meta:
        model = Course
        form = CoursesFilterForm
        fields = ('semester',)

    def __init__(self, data=None, queryset=None, request=None, **kwargs):
        if data is not None:
            data = data.copy()  # get a mutable copy of the QueryDict
        else:
            data = QueryDict(mutable=True)
        super().__init__(data=data, queryset=queryset, request=request, **kwargs)

    @property
    def form(self):
        """Attach reference to the filter set"""
        if not hasattr(self, '_form'):
            Form = self.get_form_class()
            if self.is_bound:
                self._form = Form(self.data, prefix=self.form_prefix)
            else:
                self._form = Form(prefix=self.form_prefix)
            self._form.filter_set = self
        return self._form
