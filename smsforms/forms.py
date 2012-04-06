from django import forms
from smsforms.models import DecisionTrigger

class DecisionTriggerForm(forms.ModelForm):
    class Meta(object):
        model = DecisionTrigger

