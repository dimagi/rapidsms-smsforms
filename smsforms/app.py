from rapidsms.apps.base import AppBase
from django.core.exceptions import ObjectDoesNotExist
from models import XFormsSession, DecisionTrigger
from datetime import datetime
from touchforms.formplayer import api
from touchforms.formplayer.models import XForm
import pprint

TRIGGER_KEYWORDS = {
    'fadama': '3',
    'health': '4',
    }


class TouchFormsApp(AppBase):

    @property
    def trigger_keywords(self):
        return DecisionTrigger.objects.all()

    def start(self):
        self.info('Started TouchFormsApp')

    def get_trigger_keyword(self, msg):
        """
        Scans the argument message for a trigger keyword (specified by the DecisionTrigger Model) and returns that keyword if found, else None.
        """
        if not len(msg.text):
            return None
        words = msg.text.lower().strip().split()
        first_word = words[0]
        try:
            kw = DecisionTrigger.objects.get(trigger_keyword=first_word)
            return kw
        except ObjectDoesNotExist:
            return None

    def get_session(self,msg):
        try:
            session = XFormsSession.objects.get(connection=msg.connection, ended=False)
            self.debug('Found existing session! %s' % session)
            return session
        except ObjectDoesNotExist:
            return None

    def create_session_and_save(self, msg, trigger):
        session = XFormsSession(start_time=datetime.utcnow(), modified_time=datetime.utcnow(), connection=msg.connection, ended=False, trigger=trigger)
        session.save()
        return session

    def handle(self, msg):
        def _format(text):
            # touchforms likes ints to be ints so force it if necessary
            try:
                return int(text)
            except ValueError:
                return text

        def _next(xformsresponse, message, session):
            # if there's a valid session id (typically on a new form)
            # update our mapping
            session.modified_time = datetime.utcnow()
            session.save()
            if xformsresponse.event.type == "question":
                # send the next question
                message.respond(xformsresponse.event.text_prompt)
                if xformsresponse.event.datatype == "info":
                    #We have to deal with Trigger/Label type messages expecting an 'ok' type response. So auto-send that and move on to the next question.
                    response = api.answer_question(int(session.session_id),_format('ok'))
                    return _next(response, message, session)
                return True
            elif xformsresponse.event.type == "form-complete":
                session.end_time = datetime.utcnow()
                session.ended = True
                session.save()
                return True

        new_session = False
        response = None

        #check if this Connection is in a form session:
        session = self.get_session(msg)
        trigger = self.get_trigger_keyword(msg)
        if not trigger and not session:  #obviously we hope that a trigger is not the zero ('0') character.
            return
        elif trigger and session:
            session.ended=True
            session.save()
            #mark old session as 'done' and follow process for creating a new one
            session = None

        if not trigger and session:
            trigger = session.trigger
            response = api.answer_question(int(session.session_id),_format(msg.text))
        elif trigger and not session:
            session = self.create_session_and_save(msg, trigger)
            form = trigger.xform
            new_session = True
            response = api.start_form_session(form.file.path)
            session.session_id = response.session_id
            session.save()

        return _next(response, msg, session)

