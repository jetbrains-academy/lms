import logging

from django_ses.signals import bounce_received, complaint_received

from django.db import models
from django.dispatch import receiver

from core.models import City
from notifications.service import suspend_email_address
from users.models import User

logger = logging.getLogger()


@receiver(bounce_received)
def bounce_handler(sender, mail_obj, bounce_obj, *args, **kwargs):
    """
    https://docs.aws.amazon.com/ses/latest/dg/notification-contents.html#bounce-object
    """
    if bounce_obj['bounceType'] == 'Permanent':
        for bounced_recipient in bounce_obj['bouncedRecipients']:
            email_address = bounced_recipient.pop('emailAddress')
            reason = {
                'timestamp': bounce_obj['timestamp'],
                'bounceType': bounce_obj['bounceType'],
                'bounceSubType': bounce_obj['bounceSubType'],
                **bounced_recipient
            }
            # It's possible to suspend emails in `admission.Applicant`
            # model but we should check that app is installed for the current
            # configuration
            models_to_suspend = [User]
            for model_class in models_to_suspend:
                suspend_email_address(model_class, email_address, reason)


@receiver(complaint_received)
def complaint_handler(sender, mail_obj, complaint_obj, raw_message,  *args, **kwargs):
    logger.error(complaint_obj)
