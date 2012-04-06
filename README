An alternative XForms application for RapidSMS.

Dependencies
------------
* Uses touchforms and the JavaRosa backend to play forms.  JavaRosa is included in the touchforms repository.
** For more information on the backend see: https://github.com/dimagi/touchforms
* Vellum, the XForm Designer, located at http://github.com/dimagi/vellum
** Vellum is 100% client side JavaScript.  Please make sure when you set up serving the files statically to serve them from <YOUR_DOMAIN>/formdesigner
** For dev work, see below for setup instructions.


Installation
------------
Add this project as a regular RapidSMS app.  The recommended way is to add this app as a submodule to your project and ensure that it is on the PYTHON_PATH.

In your `urls.py`, add the following:
    urlpatterns += patterns('',
        (r'^smsforms/', include('smsforms.urls'))
    )

And in `settings.py` add the following two tabs to your `RAPIDSMS_TABS`:

    ('smsforms.views.list_forms', 'Decision Tree XForms'),
    ('smsforms.views.view_triggers', 'Decision Tree Triggers'),


To serve Vellum files using Django (during development only!).  Add the following to your main urls.py:

    FORMDESIGNER_PATH = getattr(settings, 'FORMDESIGNER_ROOT', '/ABSOLUTE/PATH/TO/VELLUM_ROOT')
    if settings.DEBUG:
        urlpatterns += patterns('',
            (r'^formdesigner/(?P<path>.*)',
             'django.views.static.serve',
             {'document_root': FORMDESIGNER_PATH, 'show_indexes': True}
            ),
        )

You can now specify the location of Vellum by adding:

    FORMDESIGNER_PATH = '/some/path'

to your settings.py file (useful when multiple devs are working on the same project).


Usage
-----

Fire up your RapidSMS instance and click on the two new tabs.

#. Create a form using the FormDesigner
#. Add a trigger keyword for that form
#. Send in a message to RapidSMS (with the Message Tester or other) containing only your trigger keyword.


