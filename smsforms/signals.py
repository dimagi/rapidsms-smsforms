from django.dispatch import Signal
from touchforms.formplayer.signals import sms_form_complete
from threadless_router.router import Router

form_complete = Signal(providing_args=["session", "form", "router"])

# TODO: this is never actually raised. needs update
form_error = Signal(providing_args=["session", "form", "router"])

def handle_sms_form_complete(sender, session_id, form, **kwargs):
    """
    When touchforms completes a form via sms this signal is raised.
    
    Catch it, save our session objects, and reraise a signal of our own.
    """
    from smsforms.models import XFormsSession
    from smsforms.app import router_factory

    # implicit length assert that i'm sure is not always valid
    
    sessions = XFormsSession.objects.filter(session_id=session_id, ended=False).order_by('-modified_time')
    # there may be other open sessions so close them all
    for s in sessions:
        s.end()
        
    # the one we want to process is the most recent one though
    session = sessions[0]
    # TODO: clean up this router business
    router = router_factory.get(session.session_id)
    form_complete.send(sender="smsforms", session=session,
                       form=form, router=router)
            
sms_form_complete.connect(handle_sms_form_complete)
