# Create your views here.
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render_to_response
from django.template.context import RequestContext
from smsforms.forms import DecisionTriggerForm as DTForm
from smsforms.models import DecisionTrigger


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


def view_triggers(request):
    context = {
        'triggers': DecisionTrigger.objects.all()
    }
    return render_to_response('smsforms/view_triggers.html', context,
                              RequestContext(request))