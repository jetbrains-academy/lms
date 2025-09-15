from bitfield import BitField
from bitfield.forms import BitFieldCheckboxSelectMultiple
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models as db_models
from django.utils.translation import gettext_lazy as _

from core.timezone.forms import (
    TimezoneAwareAdminForm, TimezoneAwareAdminSplitDateTimeWidget, TimezoneAwareSplitDateTimeField
)
from core.utils import admin_datetime
from core.widgets import AdminRichTextAreaWidget
from courses.models import (
    Course, CourseClass,
    CourseClassAttachment, CourseGroupModes, CourseNews, CourseReview, CourseTeacher,
    LearningSpace, MetaCourse, Semester, CourseProgramBinding
)


class SemesterAdmin(admin.ModelAdmin):
    ordering = ('-index',)
    readonly_fields = ('starts_at', 'ends_at')


class MetaCourseAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ('name',)
    formfield_overrides = {
        db_models.TextField: {'widget': AdminRichTextAreaWidget},
    }


class CourseReviewAdmin(admin.ModelAdmin):
    search_fields = ('course__meta_course__name',)
    list_display = ('course', 'author')
    formfield_overrides = {
        db_models.TextField: {'widget': AdminRichTextAreaWidget},
    }
    raw_id_fields = ('author', 'course')


class CourseTeacherInline(admin.TabularInline):
    model = CourseTeacher
    extra = 0
    min_num = 1
    raw_id_fields = ('teacher',)
    formfield_overrides = {
        BitField: {'widget': BitFieldCheckboxSelectMultiple},
    }
    # FIXME: customize template (hide link `show on site`, now it's hidden by css)


class BaseCourseBindingInline(admin.TabularInline):
    model = CourseProgramBinding
    form = TimezoneAwareAdminForm
    extra = 0
    min_num = 0
    formfield_overrides = {
        db_models.DateTimeField: {
            'form_class': TimezoneAwareSplitDateTimeField,
            'widget': TimezoneAwareAdminSplitDateTimeWidget
        },
    }


class CourseProgramInline(BaseCourseBindingInline):
    fields = ('program', 'enrollment_end_date', 'grading_system_num', 'start_year_filter')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(invitation__isnull=True, is_alumni=False)


class CourseAdminForm(TimezoneAwareAdminForm):
    is_for_alumni = forms.BooleanField(required=False)
    alumni_enrollment_end_date = TimezoneAwareSplitDateTimeField(
        required=False,
        widget=TimezoneAwareAdminSplitDateTimeWidget(),
    )

    class Meta:
        model = Course
        fields = '__all__'

    def __init__(self, *args, instance: Course | None = None, **kwargs):
        initial = kwargs.pop('initial', {})
        if instance and (binding := instance.get_alumni_binding()):
            initial['is_for_alumni'] = True
            initial['alumni_enrollment_end_date'] = binding.enrollment_end_date
        super().__init__(*args, instance=instance, initial=initial, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        # We can select teachers only from related course offering
        if 'group_mode' in cleaned_data and cleaned_data['group_mode'] == CourseGroupModes.NO_GROUPS:
            self.add_error('group_mode', ValidationError("This mode is for internal use only"))
        if (
            cleaned_data['is_for_alumni']
            and not cleaned_data['alumni_enrollment_end_date']
        ):
            self.add_error(
                'alumni_enrollment_end_date',
                ValidationError(_('This field is required'), code='required'),
            )


class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    formfield_overrides = {
        db_models.TextField: {'widget': AdminRichTextAreaWidget},
    }
    list_filter = ['semester']
    list_display = ['meta_course', 'semester',
                    'is_published_in_video']
    inlines = (CourseProgramInline, CourseTeacherInline,)
    raw_id_fields = ('meta_course',)

    class Media:
        css = {
            'all': ('v1/css/admin/course_bindings.css', 'v1/css/admin/no_inline_form_titles.css')
        }
        js = ('v1/js/admin/course.js',)

    def save_model(self, request, obj: Course, form: CourseAdminForm, change):
        super().save_model(request, obj, form, change)
        alumni_binding = obj.get_alumni_binding()
        is_for_alumni = form.cleaned_data['is_for_alumni']
        alumni_enrollment_end_date = form.cleaned_data['alumni_enrollment_end_date']
        if alumni_binding:
            if not is_for_alumni:
                alumni_binding.delete()
            else:
                alumni_binding.enrollment_end_date = alumni_enrollment_end_date
        elif not alumni_binding and is_for_alumni:
            alumni_binding = CourseProgramBinding(
                course=obj,
                is_alumni=True,
                enrollment_end_date=alumni_enrollment_end_date,
            )
            alumni_binding.save()

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.pk is not None:
            return ['group_mode']
        return []


class LearningSpaceAdmin(admin.ModelAdmin):
    list_display = ['location', 'order']
    list_select_related = ('location',)


class CourseClassAttachmentAdmin(admin.ModelAdmin):
    list_filter = ['course_class']
    list_display = ['course_class', '__str__']


class CourseClassAttachmentInline(admin.TabularInline):
    model = CourseClassAttachment


class CourseClassAdmin(admin.ModelAdmin):
    save_as = True
    date_hierarchy = 'date'
    list_filter = ['type']
    search_fields = ['course__meta_course__name']
    list_display = ['id', 'name', 'course', 'date', 'type']
    raw_id_fields = ['venue']
    inlines = [CourseClassAttachmentInline]
    formfield_overrides = {
        db_models.TextField: {'widget': AdminRichTextAreaWidget},
    }

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'course':
            kwargs['queryset'] = (Course.objects
                                  .select_related("meta_course", "semester"))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class CourseNewsAdmin(admin.ModelAdmin):
    date_hierarchy = 'created'
    list_display = ['title', 'course', 'created_local']
    raw_id_fields = ["course", "author"]
    formfield_overrides = {
        db_models.TextField: {'widget': AdminRichTextAreaWidget},
    }

    def created_local(self, obj):
        return admin_datetime(obj.created_local())

    created_local.admin_order_field = 'created'
    created_local.short_description = _("Created")


admin.site.register(CourseReview, CourseReviewAdmin)
admin.site.register(MetaCourse, MetaCourseAdmin)
admin.site.register(Semester, SemesterAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(CourseNews, CourseNewsAdmin)
admin.site.register(LearningSpace, LearningSpaceAdmin)
admin.site.register(CourseClass, CourseClassAdmin)
admin.site.register(CourseClassAttachment, CourseClassAttachmentAdmin)
