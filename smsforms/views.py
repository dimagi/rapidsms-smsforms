# Create your views here.
from collections import defaultdict
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render_to_response
from django.template.context import RequestContext
from smsforms.forms import DecisionTriggerForm as DTForm
from smsforms.models import DecisionTrigger
from touchforms.formplayer.models import XForm
from django.utils.safestring import mark_safe


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

def list_forms(request):
    forms_by_namespace = defaultdict(list)
    success = True
    notice = ""
    for form in XForm.objects.all():
        forms_by_namespace[form.namespace].append(form)
    return render_to_response("smsforms/view_forms.html",
                              {'forms_by_namespace': dict(forms_by_namespace),
                               "success": success,
                               "notice": notice},

                              context_instance=RequestContext(request))