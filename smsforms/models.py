from django.db import models
from rapidsms.models import Connection
from touchforms.formplayer.models import XForm
from datetime import datetime

class DecisionTrigger(models.Model):
    xform = models.ForeignKey(XForm)
    trigger_keyword = models.CharField(max_length=255, help_text="The keyword you would like to trigger this form with")
    final_response = models.CharField(max_length=160, null=True, blank=True, help_text="The response to be sent when a "\
                                                                                       "form is succesfully submitted." \
                                                                                       " Leave blank for forms intended" \
                                                                                       " for decisiontree purposes.")

class XFormsSession(models.Model):
    connection = models.ForeignKey(Connection, related_name='xform_sessions')
    session_id = models.CharField(max_length=200,null=True,blank=True)
    start_time = models.DateTimeField(blank=True, null=True)
    modified_time = models.DateTimeField(blank=True, null=True)
    end_time = models.DateTimeField(blank=True, null=True)
    error_msg = models.CharField(max_length=255, null=True, blank=True, help_text="Error message last received, if any")
    has_error = models.BooleanField(default=False, help_text="Did this session have an error?")
    ended = models.BooleanField(default=False, help_text="Has this session ended?")
    trigger = models.ForeignKey(DecisionTrigger, help_text="The trigger keyword+form that triggered this session")
    cancelled = models.BooleanField(default=False, help_text="Was this session cancelled (automatically or manually)?")
    
    def __unicode__(self):
        return 'Session:: Phone Number:%s, Start Time: %s, End Time: %s, Ended?: %s' % (self.connection.identity, self.start_time, self.end_time, self.ended)

    def end(self):
        now = datetime.utcnow()
        self.end_time = now
        self.modified_time = now
        self.ended = True
        self.save()

    def cancel(self):
        self.end()
        self.cancelled = True
        self.save()
        
