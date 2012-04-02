from django import forms
from models import DecisionTrigger

class DecisionTriggerForm(forms.ModelForm):
    class Meta(object):
        model = DecisionTrigger

