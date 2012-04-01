from django.contrib import admin
from django.contrib import messages
from models import XFormsSession, DecisionTrigger

class SessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'connection','start_time', 'end_time', 'ended')
admin.site.register(XFormsSession, SessionAdmin)

class DecisionTriggerAdmin(admin.ModelAdmin):
    list_display = ('xform', 'trigger_keyword')
admin.site.register(DecisionTrigger, DecisionTriggerAdmin)
