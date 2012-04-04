from django.core.management.base import NoArgsCommand
from django.conf import settings
from rapidsms.contrib.messagelog.models import Message
from smsforms.models import XFormsSession
import datetime

DEBUG = True
DELIMETER = getattr(settings, 'SMSFORMS_REPORT_DELIMETER',',')
IS_UTCNOW = False
class Command(NoArgsCommand):
    help = 'Fetches the latest feed data for active feeds.'
    output_filename = 'smsforms_report.csv'

    def output_user(self, session, f):
        self.stdout.write('Generating data for Session: %s\n' % session)
        num = session.connection.identity
        session_id = session.session_id
        xform_name = session.trigger.xform.name
        if not IS_UTCNOW:
            hour_delta = datetime.timedelta(hours=1)
        else:
            hour_delta = datetime.timedelta(hours=0)
        time_to_complete = '-1'
        if session.ended and session.end_time:
            time_to_complete = session.end_time - session.start_time

        ###MAKE HEADER FOR METADATA ROW###
        self.stdout.write('(Writing Metadata)')
        def add_to_row(row, data):
            """
            Adds data to row seperating it with the delimeter
            """
            return "%s%s%s" % (row, DELIMETER, data)
        row = 'Session ID'
        row = add_to_row(row, 'Phone Number')
        row = add_to_row(row, 'Form Name')
        row = add_to_row(row, 'Start Time')
        row = add_to_row(row, 'End Time')
        row = add_to_row(row, 'Time To Completion (H:MM:SS)')
        row = add_to_row(row, 'Finished Form?')
        if DEBUG:
            self.stdout.write('Writing Metadata row headers to file\n')
        f.write('%s\n' % row)
        row = session_id
        row = add_to_row(row, num)
        row = add_to_row(row, xform_name)
        row = add_to_row(row, session.start_time)
        row = add_to_row(row, session.end_time)
        row = add_to_row(row, time_to_complete)
        row = add_to_row(row, session.ended)
        if DEBUG:
            self.stdout.write('Writing Metadata data row to file\n')
        f.write('%s\n' % row)

        ######MAKE MESSAGELOG DATA######
        self.stdout.write('(Writing Message Data')
        f.write('\n')
        if DEBUG:
            self.stdout.write('Getting Messagelog Messages for %s, start time=%s, end time=%s' % (num, session.start_time, session.end_time))
        if session.end_time:
            messages = Message.objects.filter(connection=session.connection, date__range=(session.start_time - hour_delta, session.end_time - hour_delta))
        else:
            messages = Message.objects.filter(connection=session.connection, date__gte=session.start_time - hour_delta)
        row = add_to_row('', 'Text')
        row = add_to_row(row, 'Date')
        row = add_to_row(row, 'Direction (In/Out)')
        if DEBUG:
            self.stdout.write('Writing Messages header row to file\n')
        f.write('%s\n' % row)

        if DEBUG:
            self.stdout.write('Writing Messages rows to file\n')
        for message in messages:
            row = add_to_row('', message.text)
            mdate = message.date + hour_delta
            row = add_to_row(row, mdate)
            row = add_to_row(row, message.direction)
            f.write('%s\n' % row)

        row = '======================'
        row = add_to_row(row, '======================================================')
        row = add_to_row(row, '=====================================')
        row = add_to_row(row, '================')
        row = add_to_row(row, '================')
        row = add_to_row(row, '================')
        row = add_to_row(row, '================')

        f.write('%s\n' % row)
        f.write('\n')

        if DEBUG:
            self.stdout.write('Done Writing Messages header row to file\n')
            self.stdout.write('Done Writing Session %s to file\n' % session)

    def handle_noargs(self, **options):
        self.stdout.write('\nCreating Report.\nOpening File: %s\n' % self.output_filename)
        file = open(self.output_filename, 'w')
        sessions = XFormsSession.objects.all()
        for session in sessions:
            self.output_user(session, file)

        file.close()

