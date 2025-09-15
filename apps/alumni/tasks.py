from django.conf import settings
from django_rq import job

from core.models import Config
from core.urls import reverse, replace_hostname
from core.utils import create_multipart_email


@job('default')
def send_alumni_promotion_email(to_email, first_name):
    consent_form_url = reverse('alumni:consent_form')
    consent_form_url = replace_hostname(consent_form_url, settings.LMS_DOMAIN)
    context = {
        'consent_form_url': consent_form_url,
        'first_name': first_name,
        'telegram_chat_url': Config.get().alumni_chat_link,
    }
    msg = create_multipart_email(
        'Welcome to JetBrains Academy Alumni Offline!',
        'emails/alumni_promotion.html',
        context,
        [to_email],
    )
    msg.send()
