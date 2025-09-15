import re
from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse as django_reverse
from django.utils.functional import lazy


def reverse(viewname, subdomain=None, scheme=None, args=None, kwargs=None,
            current_app=None):
    return django_reverse(viewname, args=args, kwargs=kwargs,
                          current_app=current_app)


reverse_lazy = lazy(reverse, str)


def replace_hostname(url, new_hostname):
    """
    `core.urls.reverse` strictly related to settings.SITE_ID value, but
    management commands could send data for different domain
    """
    parsed = urlparse(url)
    replaced = parsed._replace(netloc=new_hostname,
                               scheme=settings.DEFAULT_URL_SCHEME)
    return replaced.geturl()
