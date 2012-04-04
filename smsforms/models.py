from django.db import models
from rapidsms.models import Connection
from touchforms.formplayer.models import XForm

class DecisionTrigger(models.Model):
    xform = models.ForeignKey(XForm)
    trigger_keyword = models.CharField(max_length=255, help_text="The keyword you would like to trigger this form with")

class XFormsSession(models.Model):
    connection = models.ForeignKey(Connection, related_name='xform_sessions')
    session_id = models.CharField(max_length=200,null=True,blank=True)
    start_time = models.DateTimeField(blank=True, null=True)
    modified_time = models.DateTimeField(blank=True, null=True)
    end_time = models.DateTimeField(blank=True, null=True)
    error_msg = models.CharField(max_length=255, null=True, blank=True, help_text="Error message last received, if any")
    ended = models.BooleanField(default=False, help_text="Has this session ended?")
    trigger = models.ForeignKey(DecisionTrigger, help_text="The trigger keyword+form that triggered this session")

    def __unicode__(self):
        return 'Session:: Phone Number:%s, Start Time: %s, End Time: %s, Ended?: %s' % (self.connection.identity, self.start_time, self.end_time, self.ended)


