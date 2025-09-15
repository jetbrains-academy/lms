from django.conf import settings
from django_rq import job

from core.urls import reverse, replace_hostname
from core.utils import create_multipart_email
from users.models import City


@job('default')
def send_new_city_email(city_id):
    city = City.objects.select_related('country').get(pk=city_id)
    city_admin_url = reverse('admin:users_city_change', args=[city.pk])
    city_admin_url = replace_hostname(city_admin_url, settings.LMS_DOMAIN)
    context = {
        'city_admin_url': city_admin_url,
        'city': city,
    }
    msg = create_multipart_email(
        'LMS: New city added',
        'emails/new_city.html',
        context,
        settings.ADMIN_NOTIFICATIONS_EMAILS,
    )
    msg.send()
