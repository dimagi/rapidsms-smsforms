# Create your views here.
from collections import defaultdict
import tempfile
from django.contrib import messages
from django.core.files.base import File
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render_to_response
from django.template.context import RequestContext
import os
from smsforms.forms import DecisionTriggerForm as DTForm
from smsforms.models import DecisionTrigger
from touchforms.formplayer.models import XForm
from django.utils.safestring import mark_safe
import logging

logger = logging.getLogger('smsforms.views')
logger.setLevel(logging.DEBUG)



def edit_triggers(request, trigger_id=None):
    if trigger_id:
        trigger = get_object_or_404(DecisionTrigger, pk=trigger_id)
    else:
        trigger = None
    if request.method == 'POST':
        form = DTForm(request.POST, instance=trigger)
        if form.is_valid():
            trigger = form.save()
            if trigger_id:
                info = 'Decision Trigger successfully saved'
            else:
                info = 'Decision Trigger succesfully created'
            messages.info(request, info)
            return HttpResponseRedirect(reverse('smsforms_view-triggers'))
    else:
        form = DTForm(instance=trigger)
    context = {
        'form': form,
    }
    return render_to_response('smsforms/edit_trigger.html', context,
                              RequestContext(request))

def delete_triggers(request, trigger_id):
    trigger = get_object_or_404(DecisionTrigger, pk=trigger_id)
    info = 'Decision Trigger %s succesfully deleted' % trigger
    trigger.delete()
    messages.info(request, info)
    return HttpResponseRedirect(reverse('smsforms_view-triggers'))

def view_triggers(request):
    context = {
        'triggers': DecisionTrigger.objects.all()
    }
    return render_to_response('smsforms/view_triggers.html', context,
                              RequestContext(request))


def create_form(request, form_id=None):
    if request.method == "POST":
        return list_forms(request,form_id)
    if form_id:
        xform = get_object_or_404(XForm, id=form_id)
        lines = [line.strip() for line in xform.file.readlines()]
        xform_data = ''.join(lines).replace("'", "\\'").replace('"', '\\"')
    else:
        xform = None
        xform_data = ''

    context = {
        'xform' : xform,
        'xform_data' : mark_safe(xform_data),
    }
    return render_to_response('smsforms/create_form.html', context,
                              RequestContext(request))

def delete_form(request, form_id=None):
    xform = get_object_or_404(XForm, pk=form_id)
    info = 'XForm %s successfully deleted' % xform
    xform.delete()
    messages.info(request, info)
    return HttpResponseRedirect(reverse('smsforms_list-forms'))

def list_forms(request, form_id=None):
    def create_xform(data, name="No Name", xform_id=None):
        logging.debug('Creating or updating an xform object.  Name:%s, xform_id: %s.' % (name, xform_id))
        new_form = None
        try:
            tmp_file_handle, tmp_file_path = tempfile.mkstemp()
            logging.debug('Creating tempfile on disk')
            tmp_file = os.fdopen(tmp_file_handle, 'w')
            tmp_file.write(data)
            tmp_file.close()
            if xform_id:
                file = File(open(tmp_file_path, 'r'))
                logging.debug('Opened Temp File. Attempting to retrieve XForm object from DB. XFORM_ID IS %s' % xform_id)
                xform = get_object_or_404(XForm, id=xform_id)
                xform.file = file
                xform.save()
                success = True
                notice = "Updated form %s" % name
            else:
                logging.debug("Creating new XForm object with id: %s" % xform_id)
                new_form = XForm.from_file(tmp_file_path, name)
                notice = "Created form: %s " % name
                success = True
        except Exception, e:
            self.error("Problem creating xform from %s: %s" % (name, e))
            success = False
            notice = "Problem creating xform from %s: %s" % (name, e)
        return new_form, notice, success,

    forms_by_namespace = defaultdict(list)
    success = True
    notice = ""
    if request.method == "POST":
        logging.debug("Received POST request")
        if "file" in request.FILES:
            new_form, success, notice = create_xform(request.FILES["file"].read(), str(request.FILES["file"]), form_id)
        elif "xform" in request.POST:
            new_form, success, notice = create_xform(request.POST["xform"], request.POST["name"], form_id)
        else:
            success = False
            notice = "No uploaded file set."

    for form in XForm.objects.all():
        forms_by_namespace[form.namespace].append(form)
    return render_to_response("smsforms/view_forms.html",
                              {'forms_by_namespace': dict(forms_by_namespace),
                               "success": success,
                               "notice": notice},
                              context_instance=RequestContext(request))