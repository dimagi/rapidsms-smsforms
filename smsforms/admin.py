from django.contrib import admin
from models import XFormsSession, DecisionTrigger

class XFormsSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'connection','start_time', 'end_time',
                    'ended', 'has_error')
    list_filter = ('ended', 'has_error')

admin.site.register(XFormsSession, XFormsSessionAdmin)

class DecisionTriggerAdmin(admin.ModelAdmin):
    list_display = ('xform', 'trigger_keyword')
admin.site.register(DecisionTrigger, DecisionTriggerAdmin)
