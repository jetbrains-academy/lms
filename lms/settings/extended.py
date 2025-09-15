"""
Settings that are not used by club site
"""

from .base import *

SOCIAL_AUTH_JSONFIELD_ENABLED = True

# Registration by invitation link
INCLUDE_REGISTER_URL = False
INCLUDE_AUTH_URLS = False
ACCOUNT_ACTIVATION_DAYS = 1
ACTIVATION_EMAIL_SUBJECT = 'emails/activation_email_subject.txt'
ACTIVATION_EMAIL_BODY = 'emails/activation_email_body.txt'
