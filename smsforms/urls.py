from django.conf.urls.defaults import *
from smsforms import views


urlpatterns = patterns('',
    url(r'^edit/(?P<trigger_id>\d+)$', views.edit_triggers, name='smsforms_edit-triggers'),
    url(r'^delete/(?P<trigger_id>\d+)$', views.delete_triggers, name='smsforms_delete-triggers'),
    url(r'^view/$', views.view_triggers, name='smsforms_view-triggers'),
    url(r'^create/$', views.edit_triggers, name='smsforms_create-trigger'),

    url(r'^create_form/$', views.create_form, name='smsforms_create-form'),
    url(r'^edit_form/(?P<form_id>\d+)$', views.create_form, name='smsforms_edit-form'),
    url(r'^delete_form/(?P<form_id>\d+)$', views.delete_form, name='smsforms_delete-form'),
    url(r'^list_forms/$', views.list_forms, name='smsforms_list-forms'),
    )
