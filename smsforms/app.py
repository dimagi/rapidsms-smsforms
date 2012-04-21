from copy import copy
import json
from rapidsms.apps.base import AppBase
from django.core.exceptions import ObjectDoesNotExist
from models import XFormsSession, DecisionTrigger
from datetime import datetime
from touchforms.formplayer import api
from smsforms.signals import form_complete, form_error
import logging


logger = logging.getLogger(__name__)

class TouchFormsApp(AppBase):
    #overriding because seeing router|mixin is so unhelpful it makes me want to throw my pc out the window.
    @property
    def _logger(self):
        return logging.getLogger(__name__)

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
                return DecisionTrigger.objects.get(trigger_keyword__iexact=first_word)
            except ObjectDoesNotExist:
                return None

    def get_session(self, msg):
        try:
            session = XFormsSession.objects.get(connection=msg.connection, ended=False)
            self.debug('Found existing session! %s' % session)
            return session
        except XFormsSession.DoesNotExist:
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
        and starts the session in touchforms.
        
        Returns a tuple of the session and the touchforms response to the first
        triggering of the form.
        """
        session = self.create_session_and_save(msg, trigger)
        form = trigger.xform
        language = msg.contact.language if msg.contact else ""
        response = api.start_form_session(form.file.path, language=language)
        session.session_id = response.session_id
        session.save()
        if response.status == "http-error":
            #short circuit processing as something is jacked.
            _handle_http_error(response, session)
        return session, response
        
    def _try_process_as_whole_form(self, msg):
        """
        Try to process this message like an entire submission against an xform.
        
        Returns True if the message matches and was processed.
        """
        def _match_to_whole_form(msg):
            # for short term, the syntax for whole forms is any message with
            # more than one word in it. First word is taken as keyword and
            # the rest as answers instead of just the keyword (for interactive form entry).
            # This should be smarter, later.
            text = msg.text.strip()
            if text:
                words = text.strip().split()
                if len(words) <= 1:
                    return None
                return self.get_trigger_keyword(msg)

        def _break_into_answers(msg):
            # TODO: brittle and not fully featured
            return map(lambda ans: _tf_format(ans, fail_hard=False)[0],
                       msg.text.strip().split()[1:])

        logger.debug('Attempting to process message as WHOLE FORM')
        trigger = _match_to_whole_form(msg)
        if trigger:
            logger.debug('Trigger keyword found, attempting to answer questions...')
            # close any existing sessions
            _close_open_sessions(msg.connection)
            
            # start the form session
            session, response = self._start_session(msg, trigger)
            if response.error:
                return _respond_and_end(response.error, msg, session)
            for answer in _break_into_answers(msg):
                responses = list(_next(response, session))
                #get the last touchforms response object so that we can validate our answer
                #instead of relying on touchforms and getting back a less than useful error.
                last_response = responses.pop()
                if last_response.error:
                    return _respond_and_end(last_respons.error, msg, session)
                answer, error_msg = _tf_validate_answer(answer, last_response)
                if error_msg:
                    return _respond_and_end("%s for %s" % (error_msg, last_response.text_prompt), msg, session)

                response = api.answer_question(int(session.session_id),
                                               answer)
                if response.error:
                    return _respond_and_end("%s for %s" % (error_msg, last_response.text_prompt), msg, session)
                session.last_touchforms_response = json.dumps(response._dict)
                session.save()
                logger.debug('After answer validation. answer:%s, error_msg: %s, response: %s' % (answer, error_msg, response))
                if response.is_error or error_msg:
                    return _respond_and_end("Invalid Format for %s" % last_response.text_prompt, msg, session)

                if response.event.type == 'form-complete':
                    logger.debug('Form completed but their are extra answers. Silently dropping extras!')
                    logger.warn('Silently dropping extra answer on Full Form session! Message:%s, connection: %s' % (msg.text, msg.connection))
                    #We're done here and the session has been ended (in _next()).
                    #TODO: Should we return a response to the user warning them there are extras?
                    break
            
            # this loop just plays through the last question + any triggers
            # at the end of the form
            for response in _next(response, session):
                pass
            
            if session.ended:
                logger.debug('Session complete and marked as ended. Responding with final_response message...')
                msg.respond("%s" % trigger.final_response)
            else:
                logger.debug('Session not finished! Responding with message uncomplete: %s' % response.text_prompt)
                msg.respond("Incomplete form! The first unanswered question is '%s'." % 
                            response.text_prompt)
                # for now, manually end the session to avoid
                # confusing the session-based engine
                session.end()
                
            return True
    
    def _try_process_as_session_form(self, msg):
        """
        Try to process this message like a session-based submission against
        an xform.
        
        Returns True if the message matches and was processed.
        """
        logger.debug('Attempting to process message as SESSION FORM')
        # check if this connection is in a form session:
        session = self.get_session(msg)
        trigger = self.get_trigger_keyword(msg)
        if not trigger and session is None:
            logger.debug('Not a session form (no session or trigger kw found')
            return
        elif trigger and session:
            # mark old session as 'cancelled' and follow process for creating a new one
            logger.debug('Found trigger kw and stale session. Ending old session and starting fresh.')
            session.cancel()
            session = None

        if session:
            logger.debug('Found an existing session, attempting to answer question with message content: %s' % msg.text)
            last_response = _get_last_response_from_session(session)

            ans, error_msg = _tf_validate_answer(msg.text, last_response) #we need the last response to figure out what question type this is.
            if error_msg:
                return _respond_and_end("%s for %s" % (error_msg, last_response.text_prompt), msg, session)
            response = api.answer_question(int(session.session_id), ans)
        elif trigger:
            logger.debug('Found trigger keyword. Starting a new session')
            session, response = self._start_session(msg, trigger)
            session.last_touchforms_response = json.dumps(response._dict)
            session.save()
            if response.error:
                return _respond_and_end(response.error, msg, session)
            
        else:
            raise Exception("This is not a legal state. Some of our preconditions failed.")
        
        for xformsresponse in _next(response, session, msg):
            if xformsresponse.error:
                return _respond_and_end(xformsresponse.error, msg, session)
            if xformsresponse.text_prompt:
                msg.respond(xformsresponse.text_prompt)
            session.last_touchforms_response = json.dumps(xformsresponse._dict)
            session.save()
        logger.debug('Completed processing message as part of SESSION FORM')
        return True
    
    def handle(self, msg):
        if self._try_process_as_whole_form(msg):
            return True
        elif self._try_process_as_session_form(msg):
            return True

def _tf_validate_answer(text, response):
    """
    Attempts to do validation and formatting of the answer
    based on the response (if provided).
    If no response is provided will attempt to cast answer as an int. If this fails, returns the answer as is.
    Returns: formatted_answer, error_msg
    """

    def _validate_selects(text, response):
        """
        Prepares multi/single select answers for TouchForms.
        """
        answer_options = str(text).split() #strip happens automatically
        choices = map(lambda choice: choice.lower(), response.event.choices)
        logger.debug('Question (%s) answer choices are: %s, given answers: %s' % (datatype, choices, answer_options))
        new_answers = copy(answer_options)
        for idx, opt in enumerate(answer_options):
            logger.debug('Trying to format (m)select answer: "%s"' % opt)
            try: #in the case that we accept numbers to indicate option selection
                opt_int = int(opt)
                if not (1 <= opt_int <= len(choices)) and not opt_int in choices: #Edge case!
                    return text, 'Answer %s must be between 1 and %s' % (opt_int, len(choices))
                else:
                    new_answers[idx] = str(opt_int)

            except ValueError: #in the case where we accept the actual text of the question
                logger.debug('Caught value error, trying to parse answer string choice of: %s' % choices)
                if opt.lower() not in choices:
                    return text, 'Answer must be one of the choices'
                else:
                    new_answers[idx] = str(choices.index(opt.lower()))
        return ' '.join(new_answers), None

    logger.debug('_tf_validate_answer(%s,%s).' % (text, response))
    if not response:
        return text, 'Must Provide a XformsResponse object for answer validation!'

    datatype = response.event.datatype if response.event else None
    logger.debug('_tf_validate_answer:: Datatype is "%s"' % datatype)
    if datatype == 'int':
        return _tf_format(text,fail_hard=True)
    elif (datatype == 'select' or datatype == 'multiselect') and len(str(text).strip()): #if length is 0 will drop through to base case.
        return _validate_selects(text, response)
    else:
        return text, None


def _tf_format(text, fail_hard=False):
    try:
        return int(text), None
    except ValueError:
        error_msg = 'Answer must be a number!' if fail_hard else None
        return text, error_msg

def _next(xformsresponse, session, msg=None):
    session.modified_time = datetime.utcnow()
    session.save()
    if xformsresponse.is_error:
        yield xformsresponse
    elif xformsresponse.event.type == "question":
        yield xformsresponse
        if xformsresponse.event.datatype == "info":
            # We have to deal with Trigger/Label type messages 
            # expecting an 'ok' type response. So auto-send that 
            # and move on to the next question.
            response = api.answer_question(int(session.session_id),_tf_validate_answer('ok')[0])
            for additional_resp in _next(response, session):
                yield additional_resp
    elif xformsresponse.event.type == "form-complete":
        logger.debug('Sending FORM_COMPLETE Signal')
        form_complete.send(sender="smsforms", session=session,
                           form=xformsresponse.event.output)
        if session.trigger.final_response and msg:
            logger.debug('Found a final response, form has ended so sending it out')
            _respond_and_end(session.trigger.final_response, msg, session)
        else:
            session.end()
        yield xformsresponse

def _close_open_sessions(connection):
    sessions = XFormsSession.objects.filter(connection=connection, ended=False)
    map(lambda session: session.end(), sessions)


def _respond_and_end(text, msg, session):
    # NOTE: We auto trim the text to 160 Chars! SMS Limitations....
    logger.debug('In _respond_and_end()')
    session.end()
    msg.respond(str(text)[:159])
    return True

def _get_last_response_from_session(session):
    resp = session.last_touchforms_response
    try:
        return api.XformsResponse(json.loads(resp))
    except TypeError:
        logger.debug('Could not convert last response (saved in session object) to JSON')
        return None

def _handle_http_error(response, session):
    """
    Attempts to retrieve whatever partial XForm Instance (raw XML) may exist and posts it to couchforms.
    Also sets the session.error flag (and session.error_msg).
    """
    logger.error('HTTP ERROR: %(error)s' % response.__dict__)
    logger.error('--------------------------------------')
    logger.error('Attempting to get partial XForm instance. Response-status: %s' % response.status)
    logger.error('--------------------------------------')
    session.error = True
    session.error_msg = str(response.error)[:255] #max_length in model
    session.save()
    session_id = response.session_id or session.session_id
    if response.status == 'http-error' and session_id:
        partial = api.get_raw_instance(session_id)
        logger.error('--------------------------------------')
        logger.error('Attempted to get partial XForm instance. Content: %s' % partial)
        logger.error('--------------------------------------')
        #fire off a the partial using the form-error signal
        form_error.send(sender="smsforms", session=session,
                           form=partial)


