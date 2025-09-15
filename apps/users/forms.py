import json

import crispy_forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout
from django import forms
from django.contrib.auth.forms import UserChangeForm as _UserChangeForm
from django.contrib.auth.forms import UserCreationForm as _UserCreationForm
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _

from core.forms import CustomDateField
from core.models import LATEX_MARKDOWN_ENABLED
from core.widgets import UbereditorWidget
from users.api.serializers import CitySerializer
from users.models import User, StudentTypes, AlumniConsent, City


class CitySelectWidget(forms.TextInput):
    template_name = "users/forms/city_select_widget.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if context['widget']['value']:
            city = City.objects.get(pk=context['widget']['value'])
            city_serialized = CitySerializer(city).data
        else:
            city_serialized = None
        props = {
            'inputName': context['widget']['name'],
            'initialCity': city_serialized,
        }
        context['props_json'] = SafeString(json.dumps(props))
        return context


class UserProfileForm(forms.ModelForm):
    birth_date = CustomDateField(
        label=_("Date of Birth"),
        required=False,
    )
    alumni_consent = forms.BooleanField(
        label=_('I consent to share my contact information with other alumni'),
        required=False,
    )

    city = forms.ModelChoiceField(
        City.objects.all(),
        label='',
        widget=CitySelectWidget(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.editor = kwargs.pop('editor')
        self.student = kwargs.pop('student')
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        if not self.editor.is_curator and self.student.jetbrains_account:
            jba_field = self.fields['jetbrains_account']
            jba_field.disabled = True
            jba_field.help_text = _('To change this field, please contact your curator')

        layout_fields = list(self.fields.keys())
        self.alumni_profile = self.student.get_student_profile(
            profile_type=StudentTypes.ALUMNI
        )
        if self.alumni_profile:
            self.initial['alumni_consent'] = self.alumni_profile.alumni_consent == AlumniConsent.ACCEPTED
        else:
            layout_fields.remove('alumni_consent')
        self.helper.layout = Layout(*layout_fields)

    def save(self, commit=True):
        if self.alumni_profile:
            if self.cleaned_data['alumni_consent']:
                self.alumni_profile.alumni_consent = AlumniConsent.ACCEPTED
            else:
                self.alumni_profile.alumni_consent = AlumniConsent.DECLINED
            self.alumni_profile.save()
        return super().save(commit)

    class Meta:
        model = User
        fields = ('birth_date', 'phone', 'workplace', 'city', 'bio', 'time_zone',
                  'telegram_username', 'github_login', 'codeforces_login',
                  'jetbrains_account', 'cogniterra_user_id',
                  'linkedin_profile', 'private_contacts', 'alumni_consent')
        widgets = {
            'bio': UbereditorWidget,
            'private_contacts': UbereditorWidget,
        }
        help_texts = {
            'bio': "{}. {}".format(
                _("Tell something about yourself"),
                LATEX_MARKDOWN_ENABLED),
            'private_contacts': (
                "{}; {}"
                .format(LATEX_MARKDOWN_ENABLED,
                        _("will be shown only to logged-in users"))),
            'telegram_username': '@username in Telegram profile settings',
            'github_login': "github.com/<b>GITHUB-ID</b>",
            'stepic_id': _("stepik.org/users/<b>USER_ID</b>"),
            'codeforces_login': _("codeforces.com/profile/<b>HANDLE</b>"),
            'linkedin_profile': _("linkedin.com/in/<b>URL</b>"),
            'workplace': _("Specify one or more jobs (comma-separated)")
        }


class StudentEnrollmentFormMixin(forms.Form):
    student_id = forms.CharField(label=_('Student ID'))

    def __init__(self, *args, require_student_id: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        if not require_student_id:
            field = self.fields['student_id']
            field.required = False
            # If we delete the field from helper, the helper may become empty.
            # Empty helpers are ignored and field list is taken from the form instead
            field.widget = field.hidden_widget()
        self.helper.add_input(Submit('submit', 'Submit'))


class StudentEnrollmentForm(StudentEnrollmentFormMixin, forms.Form):
    pass


class StudentCreationForm(StudentEnrollmentFormMixin, _UserCreationForm):
    terms_accepted = forms.BooleanField(required=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'gender', 'time_zone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout.fields = [
            x for x in self.helper.layout.fields if x != 'terms_accepted'
        ]
        self.helper.layout.fields.append(
            crispy_forms.layout.Field(
                'terms_accepted',
                template='users/terms_checkbox.html'
            )
        )


class UserCreationForm(_UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email', 'gender', 'time_zone')


class UserChangeForm(_UserChangeForm):
    class Meta:
        fields = '__all__'
        model = User
