from collections import defaultdict
from zoneinfo import ZoneInfo

import datetime
import logging
import pytz
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Layout, Row, Button, Column
from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet
from django.forms.formsets import formset_factory
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from markupsafe import Markup
from typing import Any, Dict, List, Optional, Set

from core.forms import CANCEL_SAVE_PAIR, MultipleFileField, CustomDateField
from core.models import LATEX_MARKDOWN_HTML_ENABLED
from core.timezone.constants import DATE_FORMAT_RU, TIME_FORMAT_RU
from core.timezone.forms import TimezoneAwareModelForm, TimezoneAwareSplitDateTimeField
from core.timezone.utils import timezones_to_choices, UTC
from core.utils import bucketize
from core.widgets import TimeInputTextWidget, UbereditorWidget
from courses.constants import AssigneeMode, ClassTypes, AssignmentFormat
from courses.models import (
    Assignment, Course, CourseClass, CourseNews, LearningSpace, MetaCourse, CourseTeacher
)
from courses.selectors import get_course_teachers
from courses.services import CourseService

__all__ = ('MetaCourseForm', 'CourseUpdateForm', 'CourseNewsForm',
           'CourseClassForm', 'AssignmentForm', 'AssignmentResponsibleTeachersForm',
           'AssignmentResponsibleTeachersFormFactory',
           'StudentGroupAssigneeForm', 'StudentGroupAssigneeFormFactory')

from courses.utils import execution_time_string
from learning.models import StudentGroup, StudentGroupAssignee, StudentGroupTeacherBucket
from learning.services import StudentGroupService
from users.models import User

DROP_ATTACHMENT_LINK = '<a href="{}"><i class="fa fa-trash-o"></i>&nbsp;{}</a>'

logger = logging.getLogger(__name__)


class MultipleStudentGroupField(forms.TypedMultipleChoiceField):
    def __init__(self, **kwargs):
        super().__init__(coerce=int, **kwargs)

    def prepare_value(self, value):
        if not value:
            return super().prepare_value(value)
        return [
            # Initial data stores model objects
            (sg.pk if isinstance(sg, StudentGroup) else sg) for sg in value
        ]

    def widget_attrs(self, widget):
        widget_attrs = super().widget_attrs(widget)
        widget_attrs.update({
            'class': 'multiple-select bs-select-hidden',
            'title': _('To all groups'),
        })
        return widget_attrs


class MetaCourseForm(forms.ModelForm):
    name = forms.CharField(
        label=_("Course|name"),
        required=True,
        widget=forms.TextInput(attrs={'autocomplete': 'off',
                                      'autofocus': 'autofocus'}))
    description = forms.CharField(
        label=_("Course|description"),
        required=True,
        help_text=LATEX_MARKDOWN_HTML_ENABLED,
        widget=UbereditorWidget)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout.fields.append(CANCEL_SAVE_PAIR)

    class Meta:
        model = MetaCourse
        fields = ('name', 'description')


class CourseUpdateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout.fields.append(CANCEL_SAVE_PAIR)

    class Meta:
        model = Course
        fields = ['description', 'internal_description', 'contacts']
        widgets = {
            'description': UbereditorWidget,
            'internal_description': UbereditorWidget,
            'contacts': UbereditorWidget
        }


class CourseNewsForm(forms.ModelForm):
    title = forms.CharField(
        label=_("Title"),
        required=True,
        widget=forms.TextInput(attrs={'autocomplete': 'off',
                                      'autofocus': 'autofocus'}))
    text = forms.CharField(
        label=_("Text"),
        help_text=LATEX_MARKDOWN_HTML_ENABLED,
        required=True,
        widget=UbereditorWidget)

    def __init__(self, *args, **kwargs):
        course = kwargs.pop('course', None)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div('title', 'text'),
            CANCEL_SAVE_PAIR)
        super().__init__(*args, **kwargs)
        if course:
            self.instance.course = course

    class Meta:
        model = CourseNews
        fields = ['title', 'text']


class CourseClassForm(forms.ModelForm):
    venue = forms.ModelChoiceField(
        queryset=LearningSpace.objects.select_related('location'),
        label=_("Venue"),
        empty_label=None)
    type = forms.ChoiceField(
        label=_("Type"),
        choices=ClassTypes.choices)
    name = forms.CharField(
        label=_("Name"),
        widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    description = forms.CharField(
        label=_("Description"),
        required=False,
        help_text=LATEX_MARKDOWN_HTML_ENABLED,
        widget=UbereditorWidget(attrs={'autofocus': 'autofocus'}))
    slides = forms.FileField(
        label=_("Slides"),
        required=False,
        widget=forms.ClearableFileInput)
    attachments = MultipleFileField(
        label=_("Attached files"),
        required=False,
    )
    other_materials = forms.CharField(
        label=_("Other materials"),
        required=False,
        help_text=LATEX_MARKDOWN_HTML_ENABLED,
        widget=UbereditorWidget)
    date = CustomDateField(label=_("Date"))
    # TODO: validate ambiguous time points
    starts_at = forms.TimeField(
        label=_("Starts at"),
        help_text=_("Format: hh:mm"),
        widget=TimeInputTextWidget())
    ends_at = forms.TimeField(
        label=_("Ends at"),
        help_text=_("Format: hh:mm"),
        widget=TimeInputTextWidget())
    time_zone = forms.ChoiceField(
        label=_("Time Zone"),
        required=True,
        help_text=Markup('&nbsp;'))
    restricted_to = MultipleStudentGroupField(
        label=_("Student Groups"),
        required=False,
        help_text=_("Restrict course class visibility in the student schedule"))

    class Meta:
        model = CourseClass
        fields = ['venue', 'type', 'date', 'starts_at', 'ends_at', 'time_zone', 'name',
                  'description', 'slides', 'attachments', 'video_url',
                  'other_materials', 'materials_visibility', 'restricted_to']

    def __init__(self, *, course: Course, user: User, **kwargs):
        super().__init__(**kwargs)
        self.fields['venue'].queryset = (LearningSpace.objects.all())
        self.fields['time_zone'].choices = get_time_zone_choices(course, user)
        field_restrict_to = self.fields['restricted_to']
        field_restrict_to.choices = StudentGroupService.get_choices(course)
        self.instance.course = course

    def is_valid(self):
        result = super().is_valid()
        if not result:
            logger.debug(f"CourseClassForm::is_valid() errors={self.errors}")
        return result

    def clean_date(self):
        date = self.cleaned_data['date']
        # Validate this since 'course' could be invalid
        if 'course' in self.cleaned_data:
            course = self.cleaned_data['course']
            semester_start = course.semester.starts_at.date()
            semester_end = course.semester.ends_at.date()
            assert semester_start <= semester_end
            if not semester_start <= date <= semester_end:
                raise ValidationError(
                    _("Inconsistent with this course's "
                      "semester (from %(starts_at)s to %(ends_at)s)"),
                    code='date_out_of_semester',
                    params={'starts_at': semester_start,
                            'ends_at': semester_end})
        return date


class AssignmentDurationField(forms.DurationField):
    """
    Supports `hours:minutes` format instead of Django's '%d %H:%M:%S.%f'.
    """
    default_error_messages = {
        'required': _('Enter the time spent on the assignment.'),
        'invalid': _('Enter a valid duration in a HH:MM format'),
        'overflow': _('The number of days must be less than {max_days}.')
    }

    def prepare_value(self, value):
        if isinstance(value, datetime.timedelta):
            return execution_time_string(value)
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.timedelta):
            return value
        try:
            hours, minutes = map(int, str(value).split(":", maxsplit=1))
            value = datetime.timedelta(hours=hours, minutes=minutes)
        except ValueError:
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        except OverflowError:
            raise ValidationError(self.error_messages['overflow'].format(
                max_days=datetime.timedelta.max.days,
            ), code='overflow')
        if value is None:
            raise ValidationError(self.error_messages['invalid'], code='invalid')
        if value.total_seconds() < 0:
            raise ValidationError(self.error_messages['invalid'],
                                  code='invalid')
        # Intentionally don't use this value in overflow validation to be
        # more annoying for those who wants to abuse duration field
        max_days = 3
        if value.days > max_days:
            msg = _("There must be an error in the duration specified. "
                    "Please, contact curators for this problem.")
            raise ValidationError(msg, code='overflow')
        return value


class AssignmentForm(TimezoneAwareModelForm):
    prefix = "assignment"

    title = forms.CharField(
        label=_("Title"),
        widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    text = forms.CharField(
        label=_("Text"),
        help_text=LATEX_MARKDOWN_HTML_ENABLED,
        widget=UbereditorWidget(attrs={'autofocus': 'autofocus'}))
    opens_at = TimezoneAwareSplitDateTimeField(
        label=_("Opens at"),
        input_date_formats=[DATE_FORMAT_RU],
        input_time_formats=[TIME_FORMAT_RU],
        initial=timezone.now,
    )
    deadline_at = TimezoneAwareSplitDateTimeField(
        label=_("Deadline"),
        input_date_formats=[DATE_FORMAT_RU],
        input_time_formats=[TIME_FORMAT_RU],
    )
    time_zone = forms.ChoiceField(
        label=_("Time Zone"),
        required=True)
    attachments = MultipleFileField(
        label=_("Attached files"),
        required=False,
    )
    maximum_score = forms.IntegerField(
        label=_("Maximum score"),
        initial=5)
    weight = forms.DecimalField(
        label=_("Assignment Weight"),
        initial=1,
        min_value=0, max_value=1, max_digits=3, decimal_places=2,
        help_text=_("Assignment contribution to the course total score. "
                    "It takes into account in the gradebook.")
    )
    ttc = AssignmentDurationField(
        label=_("Time to Completion"),
        required=False,
        help_text=_("Estimated amount of time required for the task to be completed"),
        widget=forms.TextInput(
            attrs={"autocomplete": "off",
                   "class": "form-control",
                   "placeholder": _("hours:minutes")}))
    restricted_to = MultipleStudentGroupField(
        label=_("Available for Groups"),
        required=False,
        help_text=_("Restrict assignment to selected groups. Available to all by default."))
    assignee_mode = forms.ChoiceField(
        label=_("Assignee Mode"),
        required=True)

    def __init__(self, *, course: Course, user: User, **kwargs: Any):
        super().__init__(**kwargs)
        self.instance.course = course
        self.instance.time_zone = course.time_zone
        self.fields['ttc'].required = course.ask_ttc
        self.fields['time_zone'].choices = get_time_zone_choices(course, user)
        self.fields['assignee_mode'].choices = [
            x
            for x in AssigneeMode.choices
            if x[0] != AssigneeMode.STUDENT_GROUP_BALANCED
        ]
        # Student groups
        field_restrict_to = self.fields['restricted_to']
        field_restrict_to.choices = StudentGroupService.get_choices(course)

    class Meta:
        model = Assignment
        fields = ('title', 'text', 'opens_at', 'deadline_at', 'time_zone', 'attachments',
                  'submission_type', 'maximum_score', 'jba_course_id',
                  'weight', 'ttc', 'restricted_to', 'assignee_mode')

    def is_valid(self):
        result = super().is_valid()
        if not result:
            logger.debug(f"AssignmentForm::is_valid errors={self.errors}")
        return result

    def clean(self):
        data = super().clean()
        if data['opens_at'] >= data['deadline_at']:
            self.add_error('deadline_at', ValidationError(_('Deadline should be later than the opening date')))
        if data['submission_type'] == AssignmentFormat.JBA and data['jba_course_id'] is None:
            self.add_error('jba_course_id', ValidationError(_('This field is required')))
        if data['submission_type'] != AssignmentFormat.JBA:
            data['jba_course_id'] = None
        return data


class AssignmentResponsibleTeachersForm(forms.Form):
    prefix = "responsible"
    field_prefix = "teacher"

    @property
    def helper(self):
        helper = FormHelper()
        helper.disable_csrf = True
        helper.form_tag = False
        return helper

    def clean(self):
        data = self.to_internal()
        if not data.get('responsible_teachers'):
            raise ValidationError("Please add at least one teacher")
        return self.cleaned_data

    def to_internal(self):
        if not self.is_valid():
            return {}
        data = {'responsible_teachers': []}
        for field_name, field_value in self.cleaned_data.items():
            if field_name.startswith(self.field_prefix):
                pk, name = field_name[len(self.field_prefix) + 1:].split("-", maxsplit=1)
                if name == "active" and field_value:
                    data['responsible_teachers'].append(int(pk))
        return data


class AssignmentResponsibleTeachersFormFactory:
    field_prefix = AssignmentResponsibleTeachersForm.field_prefix

    @classmethod
    def build_form_class(cls, course: Course):
        cls_dict = {}
        # TODO: cache the result of get_course_teachers
        for course_teacher in get_course_teachers(course=course):
            key = f"{cls.field_prefix}-{course_teacher.pk}-active"
            teacher_name = course_teacher.teacher.get_full_name(last_name_first=True)
            cls_dict[key] = forms.BooleanField(label=teacher_name, required=False)
        return type("AssignmentResponsibleTeachersForm", (AssignmentResponsibleTeachersForm,), cls_dict)

    @classmethod
    def to_initial_state(cls, course: Course, assignment: Optional[Assignment] = None):
        initial = {}
        if assignment is None:
            course_teachers = list(get_course_teachers(course=course))
            selected = [ct for ct in course_teachers if ct.roles.reviewer]
        else:
            selected = assignment.assignees.all()
        for course_teacher in selected:
            initial[f"{cls.field_prefix}-{course_teacher.pk}-active"] = True
        return initial

    @classmethod
    def build_form(cls, course: Course, *, assignment: Optional[Assignment] = None,
                   **form_kwargs: Any) -> AssignmentResponsibleTeachersForm:
        form_class = cls.build_form_class(course)
        form_kwargs.setdefault("initial", cls.to_initial_state(course, assignment))
        return form_class(**form_kwargs)


class StudentGroupAssigneeForm(forms.Form):
    prefix = "student-group"
    field_prefix = "assignee"

    @property
    def helper(self):
        helper = FormHelper()
        helper.disable_csrf = True
        helper.form_tag = False
        return helper

    def to_internal(self) -> Dict[int, List[int]]:
        if not self.is_valid():
            return {}
        data = defaultdict(list)
        for field_name, field_value in self.cleaned_data.items():
            if field_name.startswith(self.field_prefix):
                pk, name = field_name[len(self.field_prefix) + 1:].split("-", maxsplit=1)
                if name == "teacher":
                    data[int(pk)].append(int(field_value))
        return data

    def is_valid(self):
        result = super().is_valid()
        if not result:
            logger.debug(f"StudentGroupAssigneeForm::isValid(): errors={self.errors}")
        return result


class StudentGroupAssigneeFormFactory:
    field_prefix = StudentGroupAssigneeForm.field_prefix

    @classmethod
    def build_form_class(cls, course: Course, is_required: bool = False):
        student_groups = CourseService.get_student_groups(course)
        course_teachers = get_course_teachers(course=course)
        cls_dict = {'student_groups': student_groups}
        choices = [
            ('', '-------'),
            *((ct.pk, ct.teacher.get_full_name(last_name_first=True))
              for ct in course_teachers)
        ]
        for student_group in student_groups:
            prefix = f"{cls.field_prefix}-{student_group.pk}"
            cls_dict[f"{prefix}-name"] = forms.CharField(label=_("Name"), max_length=255,
                                                         initial=student_group.name,
                                                         disabled=True)
            cls_dict[f"{prefix}-teacher"] = forms.ChoiceField(label=_("Teacher"),
                                                              choices=choices,
                                                              required=is_required)
        return type("StudentGroupAssigneeForm", (StudentGroupAssigneeForm,), cls_dict)

    @classmethod
    def get_initial_state(cls, course: Course,
                          assignment: Optional[Assignment] = None) -> Dict[str, int]:
        if assignment and assignment.course_id != course.pk:
            raise ValidationError(f"Assignment {assignment} is not from the course {course}")
        initial = {}
        if assignment is not None and assignment.assignee_mode == AssigneeMode.STUDENT_GROUP_CUSTOM:
            assigned_teachers = (StudentGroupAssignee.objects
                                 .filter(assignment=assignment))
            grouped = bucketize(assigned_teachers, key=lambda sga: sga.student_group_id)
            for sg_id, responsible_teachers in grouped.items():
                if len(responsible_teachers) == 1:
                    value = responsible_teachers[0].assignee_id
                    initial[f"{cls.field_prefix}-{sg_id}-teacher"] = value
        return initial

    @classmethod
    def build_form(cls, course: Course, *, is_required: bool = True,
                   assignment: Optional[Assignment] = None, **form_kwargs: Any) -> StudentGroupAssigneeForm:
        form_class = cls.build_form_class(course, is_required)
        form_kwargs.setdefault("initial", cls.get_initial_state(course, assignment))
        return form_class(**form_kwargs)


class AssignmentStudentGroupTeachersBucketForm(forms.Form):
    prefix = 'bucket'

    def __init__(self, allowed_student_groups: List[StudentGroup],
                 course_teachers: List[CourseTeacher], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student_groups'] = forms.TypedMultipleChoiceField(
            label=_("Student Groups"),
            choices=[(sg.pk, sg.get_name()) for sg in allowed_student_groups],
            coerce=int,
            required=True,
            # widget=SelectMultiple(attrs={"size": 1, "class": "bs-select-hidden multiple-select"}),
            # TODO: выбрать нормальный виджет
            # TODO: с этим виджетом проблемы, потому что id элементов при копировании сложно изменять через JS
        )
        self.fields['teachers'] = forms.TypedMultipleChoiceField(
            label=_("Teachers"),
            choices=[(ct.pk, ct.get_abbreviated_name()) for ct in course_teachers],
            coerce=int,
            # widget=SelectMultiple(attrs={"size": 1, "class": "bs-select-hidden multiple-select"}),
        )
        self.__init_helper()

    def __init_helper(self):
        self.helper = FormHelper()
        self.helper.disable_csrf = True
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column(
                    Row('student_groups'),
                    Row(
                        Button('fill_all_sg', "Fill All", css_id=f"id_{self.prefix}-FILL-SG"),
                        Button('clean_all_sg', "Clear All", css_id=f"id_{self.prefix}-CLEAR-SG")
                    ),
                    css_class="col-xs-5 m-15"
                ),
                Column(
                    Row('teachers'),
                    Row(
                        Button('fill_all_ct', "Fill All", css_id=f"id_{self.prefix}-FILL-CT"),
                        Button('clean_all_ct', "Clear All", css_id=f"id_{self.prefix}-CLEAR-CT")
                    ),
                    css_class="col-xs-5 m-10"
                ),
                Column(
                    "DELETE",
                    css_class="col-xs-1 align-self-end"
                ),
                css_class="bucket-form mb-25"
            ),
        )


class BaseAssignmentStudentGroupTeachersBucketFormSet(BaseFormSet):

    def __init__(self, course: Course,
                 available_student_groups_pk: Set[int] = None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course
        self.available_student_groups_pk = available_student_groups_pk

    def to_internal(self):
        return [
            {
                "student_groups": form.cleaned_data['student_groups'],
                "teachers": form.cleaned_data['teachers']
            } for form in self.forms if not (self.can_delete and self._should_delete_form(form))
        ]

    def clean(self):
        if any(self.errors):
            return
        course_groups = CourseService.get_student_groups(self.course)
        if not self.available_student_groups_pk:
            self.available_student_groups_pk = {sg.pk for sg in course_groups}
        labels = {sg.pk: sg.get_name() for sg in CourseService.get_student_groups(self.course)}
        assignation = dict()
        for index, form in enumerate(self.forms):
            if self.can_delete and self._should_delete_form(form):
                continue
            form_groups_pk = set(form.cleaned_data.get('student_groups', {}))
            if not form_groups_pk:
                # TODO: Браузер не передаёт данные незаполненных форм,
                #  поэтому она билдится и считается bounded и проходит валидацию
                raise ValidationError(f"Delete empty form #{index + 1}.")
            for student_group_pk in form_groups_pk:
                if student_group_pk in assignation:
                    form.add_error('student_groups',
                                   f'Student group {labels[student_group_pk]} is already added to bucket #'
                                   f'{assignation[student_group_pk] + 1}')
                elif student_group_pk not in self.available_student_groups_pk:
                    form.add_error("student_groups",
                                   f"Student group {labels[student_group_pk]} isn't included in the assignment's Available for Groups list.")
                else:
                    assignation[student_group_pk] = index
                    self.available_student_groups_pk.remove(student_group_pk)
        if self.available_student_groups_pk:
            unassigned_sg_labels = '<br> — '.join(labels[sg] for sg in self.available_student_groups_pk)
            raise ValidationError(
                f"Assign the following student groups to the buckets: <br> — {unassigned_sg_labels}.")


class AssignmentStudentGroupTeachersBucketFormSetFactory:
    prefix = AssignmentStudentGroupTeachersBucketForm.prefix

    @classmethod
    def build_formset_class(cls, assignment: Assignment):
        AssignmentStudentGroupTeachersBucketFormSet = formset_factory(
            AssignmentStudentGroupTeachersBucketForm,
            extra=0 if assignment else 1,
            formset=BaseAssignmentStudentGroupTeachersBucketFormSet,
            can_delete=True
        )
        return AssignmentStudentGroupTeachersBucketFormSet

    @classmethod
    def get_initial_state(cls, assignment: Assignment):
        buckets = StudentGroupTeacherBucket.objects.filter(assignment=assignment)
        initial = [
            {
                "student_groups": [sg.pk for sg in bucket.groups.all()],
                "teachers": [ct.pk for ct in bucket.teachers.all()]
            }
            for bucket in buckets
        ]
        return initial

    @classmethod
    def get_available_student_groups_pks(cls, assignment_form: AssignmentForm) -> Optional[Set[int]]:
        if assignment_form.is_bound:
            if assignment_form.is_valid():
                return set(assignment_form.cleaned_data['restricted_to'])
        return None

    @classmethod
    def build_formset(cls, course: Course, *, assignment: Optional[Assignment] = None,
                      assignment_form: AssignmentForm,
                      **formset_kwargs: Any) -> BaseAssignmentStudentGroupTeachersBucketFormSet:
        all_student_groups = CourseService.get_student_groups(course)
        course_teachers = get_course_teachers(course=course)
        formset_class = cls.build_formset_class(assignment)
        form_kwargs = {
            "allowed_student_groups": all_student_groups,
            "course_teachers": course_teachers
        }
        if assignment and not formset_kwargs.get('data'):
            initial = cls.get_initial_state(assignment)
            formset_kwargs.setdefault('initial', initial)
        available_sgs = cls.get_available_student_groups_pks(assignment_form)
        buckets_formset = formset_class(
            course,
            available_student_groups_pk=available_sgs,
            prefix=cls.prefix,
            form_kwargs=form_kwargs,
            **formset_kwargs
        )
        return buckets_formset

def get_time_zone_choices(course: Course, user: User) -> list[tuple[str, str]]:
    top_choices = timezones_to_choices(
        CourseService.get_time_zones(course) | {user.time_zone},
    )
    bottom_choices = timezones_to_choices(ZoneInfo(x) for x in pytz.common_timezones)
    return top_choices + [(None, '------')] + bottom_choices
