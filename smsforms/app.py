from copy import copy
import json
from rapidsms.apps.base import AppBase
from django.core.exceptions import ObjectDoesNotExist
from .models import XFormsSession, DecisionTrigger
from datetime import datetime
from touchforms.formplayer import api
from touchforms.formplayer import sms as tfsms
from smsforms.signals import form_complete, form_error
import logging
from touchforms.formplayer.api import XFormsConfig

_ = lambda s: s

logger = logging.getLogger(__name__)

class SessionRouterCache():
    """
    This is pretty ghetto. In order to manage different routers and allow
    tests to pass we need a global way to get the right router that triggered
    a message, so use this cache object.
    """
    cache = {}
    
    def set(self, session_id, router):
        session_id = int(session_id)
        self.cache[session_id] = router
        
    def get(self, session_id):
        session_id = int(session_id)
        if session_id not in self.cache:
            raise ValueError("No router value found for session %s" % session_id)
        return self.cache[session_id]

# see above
router_factory = SessionRouterCache()
    
class TouchFormsApp(AppBase):
        
    # overriding because seeing router|mixin is not helpful 
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
        except ObjectDoesNotExist:
            return None

    
        
    def _start_session(self, msg, trigger):
        """
        Starts a new touchforms session. Creates the session object in the db
        and starts the session in touchforms.
        
        Returns a tuple of the session and the touchforms response to the first
        triggering of the form.
        """
        form = trigger.xform
        language = msg.contact.language if msg.contact else ""
        now = datetime.utcnow()
        
        # start session in touchforms
        config = XFormsConfig(form_path=form.file.path, 
                              language=language)
        session_id, responses = tfsms.start_session(config)
        
        # save session in our data models
        session = XFormsSession(start_time=now, modified_time=now, 
                                session_id=session_id,
                                connection=msg.connection, ended=False, 
                                trigger=trigger)
        session.save()
        router_factory.set(session_id, self.router)
        return session, responses
        
    def _try_process_as_whole_form(self, msg):
        """
        Try to process this message like an entire submission against an xform.
        
        Returns True if the message matches and was processed.
        """
        def _match_to_whole_form(msg):
            # for short term, the syntax for whole forms is any message with
            # more than one word in it. First word is taken as keyword and
            # the rest as answers instead of just the keyword (for interactive
            # form entry). This should be smarter, later.
            text = msg.text.strip()
            if text:
                words = text.strip().split()
                if len(words) > 1:
                    return self.get_trigger_keyword(msg)
            return None

        def _break_into_answers(msg):
            # TODO: brittle and not fully featured
            return map(lambda ans: _tf_format(ans)[0],
                       msg.text.strip().split()[1:])

        trigger = _match_to_whole_form(msg)
        if not trigger:
            return
        
        # close any existing sessions
        _close_open_sessions(msg.connection)

        # start the form session
        session, responses = self._start_session(msg, trigger)
        assert len(responses) > 0, "there should be at least 1 response"
        if responses[0].is_error:
            # if the initial session fails, just close the session immediately
            # and return the error
            session.end()
            msg.respond(responses.error)
            return True
        
        # loop through answers
        current_question = list(responses)[-1]
        answers = _break_into_answers(msg)
        for i, answer in enumerate(answers):
            logging.debug('Processing answer: %s' % answer)
            
            # Attempt to clean and validate given answer before sending to TF
            answer, validation_error_msg = _pre_validate_answer(answer, current_question)
            if validation_error_msg:
                return _respond_and_end("%s for \"%s\"" % (validation_error_msg, current_question.text_prompt), msg, session)

            responses = tfsms.next_responses(int(session.session_id), answer)
            current_question = list(responses)[-1]               
            
            # get the last touchforms response object so that we can validate our answer
            # instead of relying on touchforms and getting back a less than useful error.
            if _handle_xformresponse_error(current_question, msg, session, self.router):
                return True
            
            if i+1 != len(answers) and current_question.event and \
                        current_question.event.type == 'form-complete':
                logger.debug('Form completed but their are extra answers. Silently dropping extras! %s' % (", ".join(answers[i-1:])))
                logger.warn('Silently dropping extra answer on Full Form session! Message:%s, connection: %s' % (msg.text, msg.connection))
                # We're done here and the session has been ended (in _next()).
                # TODO: Should we return a response to the user warning them there are extras?
                break

        # play through the remaining questions at the end of the form
        # and if they are all optional, answer them with blanks and 
        # finish.
        session = XFormsSession.objects.get(pk=session.pk)
        if not session.ended: # and trigger.allow_incomplete:
            while not session.ended and responses:
                responses = tfsms.next_responses(int(session.session_id), "")
                current_question = list(responses)[-1]               
                
                # if any of the remaining items complain about an empty
                # answer, send the response
                if _handle_xformresponse_error(current_question, msg, session, self.router):
                    return True
                
                session = XFormsSession.objects.get(pk=session.pk)
            
        session = XFormsSession.objects.get(pk=session.pk)
        if not session.ended:
            logger.debug('Session not finished! Responding with message incomplete: %s' % current_question.text_prompt)
            msg.respond("Incomplete form! The first unanswered question is '%s'." %
                        current_question.text_prompt)
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
            last_response = api.current_question(int(session.session_id))
            ans, error_msg = _pre_validate_answer(msg.text, last_response) 
            # we need the last response to figure out what question type this is.
            if error_msg:
                msg.respond("%s for \"%s\"" % (error_msg, last_response.text_prompt))
                return True             
            
            responses = tfsms.next_responses(int(session.session_id), ans, auth=None)
            
        
        elif trigger:
            logger.debug('Found trigger keyword. Starting a new session')
            session, responses = self._start_session(msg, trigger)
        
        else:
            raise Exception("This is not a legal state. Some of our preconditions failed.")
        
        [msg.respond(resp.text_prompt) for resp in responses if resp.text_prompt]
        logger.debug('Completed processing message as part of SESSION FORM')
        return True
    
    def handle(self, msg):
        if self._try_process_as_whole_form(msg):
            return True
        elif self._try_process_as_session_form(msg):
            return True

def _pre_validate_answer(text, response):
    """
    Attempts to do validation and formatting of the answer based on the 
    response (if provided).
    
    If no response is provided will attempt to cast answer as an int. 
    If this fails, returns the answer as is.
    
    Returns: formatted_answer, error_msg
    """

    def _validate_selects(text, response):
        """
        Prepares multi/single select answers for TouchForms.
        """
        answer_options = str(text).split()
        choices = map(lambda choice: choice.lower(), response.event.choices)
        logger.debug('Question (%s) answer choices are: %s, given answers: %s' % (datatype, choices, answer_options))
        new_answers = copy(answer_options)
        for idx, opt in enumerate(answer_options):
            logger.debug('Trying to format (m)select answer: "%s"' % opt)
            try: 
                #in the case that we accept numbers to indicate option selection
                opt_int = int(opt)
                if not (1 <= opt_int <= len(choices)): 
                    return text, 'Answer %s must be between 1 and %s' % (opt_int, len(choices))
                else:
                    new_answers[idx] = str(opt_int)

            except ValueError: 
                # in the case where we accept the actual text of the question
                logger.debug('Caught value error, trying to parse answer string choice of: %s' % choices)
                if opt.lower() not in choices:
                    return text, 'Answer must be one of the choices'
                else:
                    new_answers[idx] = str(choices.index(opt.lower()) + 1)
        return ' '.join(new_answers), None

    if not response:
        return text, 'Must Provide a XformsResponse object for answer validation!'

    datatype = response.event.datatype if response.event else None
    logger.debug('_pre_validate_answer:: Datatype is "%s"' % datatype)
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

def _handle_xformresponse_error(response, msg, session, router, answer=None):
    """
    Attempts to retrieve whatever partial XForm Instance (raw XML) may exist 
    and posts it to couchforms.
    
    Also sets the session.error flag (and session.error_msg).
    """
    if not response.is_error:
        return
    session.error = True
    session.error_msg = str(response.error)[:255] #max_length in model
    session.save()
    session_id = response.session_id or session.session_id
    if response.status == 'http-error':
        # TODO: translate / customize
        err_resp = _("There was a server error. Please try again later")
        if session_id:
            partial = api.get_raw_instance(session_id)
            logger.error('HTTP ERROR. Attempted to get partial XForm instance. Content: %s' % partial)
            if partial:
                # fire off a the partial using the form-error signal
                form_error.send(sender="smsforms", session=session,form=unicode(partial).strip(), router=router)
            return _respond_and_end(err_resp, msg, session)
        else:
            msg.respond(err_resp)
            return True
    elif response.status == 'validation-error' and session:
        logger.debug('Handling Validation Error')
        last_response = _get_last_response_from_session(session)
        if last_response.event and last_response.event.text_prompt:
            if answer:
                ret_msg = '%s:"%s" in "%s"' % (response.error, answer, last_response.event.text_prompt)
            else:
                ret_msg = '%s for "%s"' % (response.error, last_response.event.text_prompt)
        else:
            ret_msg = response.error
        return _respond_and_end(ret_msg, msg, session)
