from rapidsms.apps.base import AppBase
from rapidsms.models import Contact
from touchforms.formplayer import api
from touchforms.formplayer.models import XForm


class App(AppBase):
    def start (self):
        """Configure your app in the start phase."""
        self.active_sessions = {}

    def parse (self, message):
        """Parse and annotate messages in the parse phase."""
        pass

    def handle (self, message):
        """Add your main application logic in the handle phase."""
        
        def _next(xformsresponse, message):
            # if there's a valid session id (typically on a new form)
            # update our mapping
            if xformsresponse.event.type == "question":
                # send the next question
                message.respond(xformsresponse.event.text_prompt)
                return True
            elif xformsresponse.event.type == "form-complete":
                message.respond("you're done! thanks!")
                del self.active_sessions[message.connection]
                return True
        
                
        if message.text.lower().startswith("play"):
            # todo, validation/error handling
            form_id = int(message.text.split()[1])
            form = XForm.objects.get(pk=form_id)
            response = api.start_form_session(form.file.path)
            self.active_sessions[message.connection] = response.session_id
            return _next(response, message)
            
        elif message.connection in self.active_sessions:
            def _format(text):
                # touchforms likes ints to be ints so force it if necessary
                try:
                    return int(text)
                except ValueError:
                    return text
            
            response = api.answer_question(self.active_sessions[message.connection],
                                           _format(message.text))
            return _next(response, message)
            
    def cleanup (self, message):
        """Perform any clean up after all handlers have run in the
           cleanup phase."""
        pass

    def outgoing (self, message):
        """Handle outgoing message notifications."""
        pass

    def stop (self):
        """Perform global app cleanup when the application is stopped."""
        pass
