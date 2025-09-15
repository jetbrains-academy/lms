from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as _UserAdmin
from django.core.exceptions import ValidationError
from django.db import models as db_models
from django.utils import formats
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportMixin

from core.admin import BaseModelAdmin, meta
from core.widgets import AdminRichTextAreaWidget
from learning.settings import StudentStatuses
from users.constants import student_permission_roles
from users.forms import UserChangeForm, UserCreationForm
from .import_export import UserRecordResource
from .models import (
    StudentProfile, StudentStatusLog, StudentTypes, User, UserGroup, SubmissionForm, Country, City
)
from .services import assign_role, update_student_status


class UserGroupForm(forms.ModelForm):
    """Form for adding new Course Access Roles view the Django Admin Panel."""

    class Meta:
        model = UserGroup
        fields = ('role',)

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data['user']
        permission_role = cleaned_data.get('role')
        if permission_role:
            permission_role = int(permission_role)
            if permission_role in student_permission_roles:
                profile_type = StudentTypes.from_permission_role(permission_role)
                student_profile = user.get_student_profile(profile_type=profile_type)
                if not student_profile:
                    msg = _("Create Student Profile before adding student "
                            "permissions")
                    self.add_error(None, ValidationError(msg))


class UserGroupInlineAdmin(admin.TabularInline):
    form = UserGroupForm
    model = UserGroup
    extra = 0
    insert_after_fieldset = _('Permissions')

    class Media:
        css = {
            'all': ('v1/css/admin/no_inline_form_titles.css',)
        }


class UserAdmin(_UserAdmin):
    add_form = UserCreationForm
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name',
                       'password1', 'password2', 'gender', 'time_zone'),
        }),
    )
    form = UserChangeForm
    change_form_template = 'admin/user_change_form.html'
    ordering = ['last_name', 'first_name']
    inlines = [UserGroupInlineAdmin]
    readonly_fields = ['last_login', 'date_joined']
    list_display = ['id', 'username', 'email', 'first_name', 'last_name',
                    'is_staff']
    list_filter = ['is_active', 'group__site', 'group__role',
                   'is_staff', 'is_superuser']
    filter_horizontal = []

    formfield_overrides = {
        db_models.TextField: {'widget': AdminRichTextAreaWidget},
    }

    fieldsets = [
        (None, {'fields': ('username', 'email', 'password')}),
        (_('Personal info'), {
            'fields': ['gender', 'birth_date',
                       'last_name', 'first_name', 'phone',
                       'workplace', 'city', 'photo', 'bio', 'private_contacts',
                       'time_zone']}),
        (_('Permissions'), {'fields': ['is_active', 'is_staff', 'is_superuser',
                                       ]}),
        (_('External services'), {'fields': [
            'telegram_username', 'github_login', 'codeforces_login',
            'jetbrains_account', 'cogniterra_user_id',
            'linkedin_profile'
        ]}),
        (_('Important dates'), {'fields': ['last_login', 'date_joined']})]

    def get_formsets_with_inlines(self, request, obj=None):
        """
        Yield formsets and the corresponding inlines.
        """
        if obj is None:
            return None
        for inline in self.get_inline_instances(request, obj):
            yield inline.get_formset(request, obj), inline

    def save_model(self, request, obj, form, change):
        if "comment" in form.changed_data:
            obj.comment_last_author = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        formset.save()


class StudentStatusLogAdminInline(admin.TabularInline):
    list_select_related = ['student_profile', 'entry_author']
    model = StudentStatusLog
    extra = 0
    show_change_link = True
    readonly_fields = ('get_semester', 'status', 'entry_author')
    ordering = ['-status_changed_at', '-pk']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @meta(_("Semester"))
    def get_semester(self, obj):
        from courses.utils import get_terms_in_range
        changed_at = obj.status_changed_at
        term = next(get_terms_in_range(changed_at, changed_at), None)
        return term.label if term else '-'


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        profile_type = cleaned_data.get('type')
        user = cleaned_data.get('user')
        year_of_admission = cleaned_data.get('year_of_admission')
        required_for_validation = [user, year_of_admission]
        if all(f for f in required_for_validation):
            # Show user-friendly error if unique constraint is failed
            if profile_type == StudentTypes.REGULAR:
                profile = (StudentProfile.objects
                           .filter(user=user,
                                   type=StudentTypes.REGULAR,
                                   year_of_admission=year_of_admission))
                if profile.exists():
                    msg = _('Regular student profile already exists for this '
                            'admission campaign year.')
                    self.add_error('year_of_admission', ValidationError(msg))


class StudentProfileAdmin(BaseModelAdmin):
    form = StudentProfileForm
    list_select_related = ['user']
    list_display = ('user', 'type', 'year_of_admission', 'year_of_graduation', 'status', 'priority')
    list_filter = ('type', 'status',)
    raw_id_fields = ('user', 'comment_last_author')
    search_fields = ['user__last_name']
    inlines = [StudentStatusLogAdminInline]
    fieldsets = [
        (None, {
            'fields': ['type', 'is_paid_basis', 'user', 'status',
                       'year_of_admission', 'year_of_graduation',
                       'academic_program_enrollment',
                       'invitation', 'university', 'academic_disciplines',
                       'alumni_consent']
        }),
        (_("Curator's note"), {
            'fields': ['comment', 'comment_changed_at', 'comment_last_author']
        }),
    ]

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.pk:
            # TODO: add user change url
            return ['type', 'year_of_admission', 'birth_date',
                    'comment_changed_at', 'comment_last_author',
                    'invitation', 'academic_program_enrollment']
        return ['birth_date']

    def save_model(self, request, obj: StudentProfile,
                   form: StudentProfileForm, change: bool) -> None:
        if "comment" in form.changed_data:
            obj.comment_last_author = request.user
        if change:
            if "status" in form.changed_data:
                update_student_status(obj, new_status=form.cleaned_data['status'],
                                      editor=request.user)
        super().save_model(request, obj, form, change)
        if not change and obj.status not in StudentStatuses.inactive_statuses:
            permission_role = StudentTypes.to_permission_role(obj.type)
            assign_role(account=obj.user, role=permission_role)

    @admin.display(description=_("Date of Birth"))
    def birth_date(self, obj):
        if obj.user_id and obj.user.birth_date:
            d = formats.date_format(obj.user.birth_date, 'd.m.Y')
            return mark_safe(d)
        return "Not specified"


class UserRecordResourceAdmin(ImportMixin, UserAdmin):
    resource_class = UserRecordResource
    import_template_name = 'admin/import_export/import_users.html'


class CertificateOfParticipationAdmin(admin.ModelAdmin):
    list_display = ["student_profile", "created"]
    raw_id_fields = ["student_profile"]


class SubmissionFormAdmin(admin.ModelAdmin):
    list_display = ["academic_program_run"]


admin.site.register(User, UserRecordResourceAdmin)
admin.site.register(StudentProfile, StudentProfileAdmin)
admin.site.register(SubmissionForm, SubmissionFormAdmin)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['name', 'country']
