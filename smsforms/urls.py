from django.conf.urls.defaults import *
from smsforms import views


urlpatterns = patterns('',
    url(r'^edit/(?P<trigger_id>\d+)$', views.edit_triggers, name='smsforms_edit-triggers'),
    url(r'^view/$', views.view_triggers, name='smsforms_view-triggers'),
    url(r'^create/$', views.edit_triggers, name='smsforms_create-trigger'),
    url(r'^create_form/$', views.create_form, name='smsforms_create-form'),
    )