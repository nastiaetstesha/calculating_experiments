from django import forms
from .models import Experiment

class ExperimentImportForm(forms.Form):
    json_file = forms.FileField(required=False)
    json_text = forms.CharField(widget=forms.Textarea, required=False)

    def clean(self):
        data = super().clean()
        if not data.get('json_file') and not data.get('json_text'):
            raise forms.ValidationError('Загрузите файл или вставьте JSON')
        return data


class ExperimentSelectForm(forms.Form):
    finished = forms.BooleanField(required=False, label='Расчёты завершены')
    experiment = forms.ModelChoiceField(
        queryset=Experiment.objects.none(),
        required=False,
        label='Эксперимент'
    )
