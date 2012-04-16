from rapidsms.apps.base import AppBase
from django.core.exceptions import ObjectDoesNotExist
from models import XFormsSession, DecisionTrigger
from datetime import datetime
from touchforms.formplayer import api
from smsforms.signals import form_complete

class TouchFormsApp(AppBase):

    @property
    def trigger_keywords(self):
        return DecisionTrigger.objects.all()

    def start(self):
        self.info('Started TouchFormsApp')

    def get_trigger_keyword(self, msg):
        """
        Scans the argument message for a trigger keyword (specified by the 
        DecisionTrigger Model) and returns that keyword if found, else None.
        """
        if msg.text.strip():
            first_word = msg.text.lower().strip().split()[0]
            try:
                return DecisionTrigger.objects.get(trigger_keyword=first_word)
            except ObjectDoesNotExist:
                return None

    def get_session(self, msg):
        try:
            session = XFormsSession.objects.get(connection=msg.connection, ended=False)
            self.debug('Found existing session! %s' % session)
            return session
        except ObjectDoesNotExist:
            return None

    def create_session_and_save(self, msg, trigger):
        now = datetime.utcnow()
        session = XFormsSession(start_time=now, modified_time=now, 
                                connection=msg.connection, ended=False, 
                                trigger=trigger)
        session.save()
        return session

    def _start_session(self, msg, trigger):
        """
        Starts a new touchforms session. Creates the session object in the db
        ant starts the session in touchforms.
        
        Returns a tuple of the session and the touchforms response to the first
        triggering of the form.
        """
        session = self.create_session_and_save(msg, trigger)
        form = trigger.xform
        response = api.start_form_session(form.file.path)
        session.session_id = response.session_id
        session.save()
        return (session, response)
        
    def _try_process_as_whole_form(self, msg):
        """
        Try to process this message like an entire submission against an xform.
        
        Returns True if the message matches and was processed.
        """
        def _match_to_whole_form(msg):
            # for short term, the syntax for whole forms is +keyword
            # instead of keyword. this should be smarter, later.
            text = msg.text.strip()
            if text:
                kwcandidate = text.strip().split()[0]
                if kwcandidate.startswith("+"):
                    try:
                        return DecisionTrigger.objects.get \
                            (trigger_keyword=kwcandidate[1:])
                    except DecisionTrigger.DoesNotExist:
                        return None

        def _break_into_answers(msg):
            # TODO: brittle and not fully featured
            return map(lambda ans: _tf_format(ans),
                       msg.text.strip().split()[1:])
            
        trigger = _match_to_whole_form(msg)
        if trigger:
            # start the form session
            session, response = self._start_session(msg, trigger)
            for answer in _break_into_answers(msg):
                responses = list(_next(response, session))
                response = api.answer_question(int(session.session_id),
                                               answer)
            
            # this loop just plays through the last question + any triggers
            # at the end of the form
            for response in _next(response, session):
                pass
            
            if session.ended:
                msg.respond("%s received. Thanks!" % trigger.trigger_keyword)
            else:
                msg.respond("Incomplete form! The first unanswered question is '%s'." % 
                            response.event.text_prompt)
            return True
    
    def _try_process_as_session_form(self, msg):
        """
        Try to process this message like a session-based submission against
        an xform.
        
        Returns True if the message matches and was processed.
        """
        
        # check if this connection is in a form session:
        session = self.get_session(msg)
        trigger = self.get_trigger_keyword(msg)
        if not trigger and session is None:  
            return
        elif trigger and session:
            # mark old session as 'done' and follow process for creating a new one
            # TODO: should probably have a way to mark as canceled.
            session.ended = True
            session.save()
            session = None

        if session:
            response = api.answer_question(int(session.session_id),_tf_format(msg.text))
        elif trigger:
            session, response = self._start_session(msg, trigger)
            
        else:
            raise Exception("This is not a legal state. Some of our preconditions failed.")
        
        for xformsresponse in _next(response, session):
            if xformsresponse.event.text_prompt:
                msg.respond(xformsresponse.event.text_prompt)
        return True
    
    def handle(self, msg):
        if self._try_process_as_whole_form(msg):
            return True
        elif self._try_process_as_session_form(msg):
            return True
        
        
def _tf_format(text):
    # touchforms likes ints to be ints so force it if necessary.
    # any additional formatting needs can go here if they come up
    try:
        return int(text)
    except ValueError:
        return text

def _next(xformsresponse, session):
    now = datetime.utcnow()
    session.modified_time = now
    session.save()
    if xformsresponse.event.type == "question":
        yield xformsresponse
        if xformsresponse.event.datatype == "info":
            # We have to deal with Trigger/Label type messages 
            # expecting an 'ok' type response. So auto-send that 
            # and move on to the next question.
            response = api.answer_question(int(session.session_id),_tf_format('ok'))
            for additional_resp in _next(response, session):
                yield additional_resp
    elif xformsresponse.event.type == "form-complete":
        session.end_time = now
        session.ended = True
        session.save()
        form_complete.send(sender="smsforms", session=session,
                           form=xformsresponse.event.output)
        yield xformsresponse

