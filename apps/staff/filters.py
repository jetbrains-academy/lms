from typing import List

import django_filters
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Layout, Row, Submit
from django.utils.translation import gettext_lazy as _

from core.models import University
from users.models import StudentProfile, StudentTypes


class StudentProfileFilter(django_filters.FilterSet):
    university = django_filters.ChoiceFilter(
        field_name='academic_program_enrollment__program__university',
        label="University",
        required=True,
        empty_label=None,
        choices=())
    year = django_filters.TypedChoiceFilter(
        label="Year of admission",
        field_name="year_of_admission",
        required=True,
        coerce=int)
    type = django_filters.ChoiceFilter(
        label="Profile Type",
        required=False,
        choices=StudentTypes.choices)

    class Meta:
        model = StudentProfile
        fields = ['year', 'university', 'type']

    def __init__(self, universities: List[University], data=None, **kwargs):
        assert len(universities) > 0
        super().__init__(data=data, **kwargs)
        self.filters['university'].extra["choices"] = [(b.pk, b.name) for b in universities]
        years = (
            StudentProfile.objects
            .order_by('-year_of_admission')
            .values_list('year_of_admission')
            .distinct()
        )
        self.filters['year'].extra["choices"] = [(y[0], y[0]) for y in years]

    @property
    def form(self):
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper = FormHelper()
            self._form.helper.form_method = "GET"
            self._form.helper.layout = Layout(
                Row(
                    Div("university", css_class="col-xs-3"),
                    Div("year", css_class="col-xs-3"),
                    Div("type", css_class="col-xs-3"),
                    Div(Submit('', _('Filter'), css_class="btn-block -inline-submit"),
                        css_class="col-xs-3"),
                ))
        return self._form

    @property
    def qs(self):
        # Prevents returning all records
        if not self.is_bound or not self.is_valid():
            return self.queryset.none()
        return super().qs


class EnrollmentInvitationFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        label="Name",
        lookup_expr='icontains'
    )

    class Meta:
        model = StudentProfile
        fields = ['name']

    def __init__(self, data=None, **kwargs):
        super().__init__(data=data, **kwargs)

    @property
    def form(self):
        if not hasattr(self, '_form'):
            self._form = super().form
            self._form.helper = FormHelper()
            self._form.helper.form_method = "GET"
            self._form.helper.layout = Layout(
                Row(
                    Div("name", css_class="col-xs-6"),
                    Div(Submit('', _('Filter'), css_class="btn-block -inline-submit"),
                        css_class="col-xs-3"),
                ))
        return self._form

    @property
    def qs(self):
        # Do not return all records by default
        if not self.is_bound or not self.is_valid():
            return self.queryset.none()
        return super().qs
