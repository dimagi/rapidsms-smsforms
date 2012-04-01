from django.conf.urls.defaults import *
from aremind.apps.smstouchforms import views


urlpatterns = patterns('',
    url(r'^edit/$', views.edit_triggers, name='edit-triggers'),
    url(r'^view/$', views.view_triggers, name='view-triggers'),
    )