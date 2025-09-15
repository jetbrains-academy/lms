import pytest
from django import forms

from core.forms import CustomDateField


def test_custom_date_field():
    field = CustomDateField()
    field.clean('30.01.2024')
    with pytest.raises(forms.ValidationError):
        field.clean('30/01/2024')
    with pytest.raises(forms.ValidationError):
        field.clean('01/30/2024')
