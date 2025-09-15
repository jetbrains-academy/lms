from crispy_forms.layout import Button, Div, Submit
from django import forms
from django.conf import settings
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from core.timezone.constants import DATE_FORMAT_RU
from core.widgets import MultipleFileInput, DateInputTextWidget

CANCEL_BUTTON = Button(
    'cancel', _('Cancel'), onclick='history.go(-1);', css_class="btn btn-default"
)
SUBMIT_BUTTON = Submit('save', _('Save'))
CANCEL_SAVE_PAIR = Div(CANCEL_BUTTON, SUBMIT_BUTTON, css_class="pull-right")


class ScoreField(forms.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("min_value", 0)
        kwargs.setdefault("max_digits", 6)
        kwargs.setdefault("decimal_places", 2)
        widget = forms.NumberInput(attrs={'min': 0, 'step': 0.01})
        kwargs.setdefault("widget", widget)
        super().__init__(*args, **kwargs)

    def clean(self, value):
        """Allow using `1.23` and `1,23` string values"""
        if value not in self.empty_values and hasattr(value, "replace"):
            value = value.replace(",", ".")
        return super().clean(value)


# https://docs.djangoproject.com/en/4.2/topics/http/file-uploads/#uploading-multiple-files
class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        kwargs.setdefault(
            'help_text',
            _("You can select multiple files (up to %(size)s each)")
            % {'size': str(settings.FILE_MAX_UPLOAD_SIZE // 1024 // 1024) + ' MiB'},
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


class CustomDateField(forms.DateField):
    def __init__(self, **kwargs):
        kwargs.setdefault('help_text', _("Format: dd.mm.yyyy"))
        kwargs.setdefault('widget', DateInputTextWidget(attrs={'class': 'datepicker'}))
        kwargs.setdefault('input_formats', [DATE_FORMAT_RU])
        super().__init__(**kwargs)
