from base64 import urlsafe_b64encode
from typing import Dict, NamedTuple, NewType, Union

from bitfield import BitField
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.encoding import force_bytes, force_str, smart_str
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from markupsafe import Markup
from model_utils.fields import AutoCreatedField, AutoLastModifiedField

from core.db.fields import TimeZoneField
from core.db.models import ConfigurationModel
from core.timezone import TimezoneAwareMixin
from core.urls import reverse


class BranchNaturalKey(NamedTuple):
    code: str
    site_id: int


SiteId = NewType('SiteId', int)

# TODO: Move to shared cache since it's hard to clear in all processes
SITE_CONFIGURATION_CACHE = {}

LATEX_MARKDOWN_HTML_ENABLED = Markup(_(
    'Read how to style the text '
    '<a href="/commenting-the-right-way/" target="_blank">here</a>. '
    'HTML is partially enabled too.'
))
LATEX_MARKDOWN_ENABLED = Markup(_(
    'Read how to style the text '
    '<a href="/commenting-the-right-way/" target="_blank">here</a>.'
))


class SiteConfigurationManager(models.Manager):
    use_in_migrations = False

    def get_by_site_id(self, site_id: int) -> "SiteConfiguration":
        if site_id not in SITE_CONFIGURATION_CACHE:
            site_configuration = self.get(site_id=site_id)
            SITE_CONFIGURATION_CACHE[site_id] = site_configuration
        return SITE_CONFIGURATION_CACHE[site_id]

    def get_current(self, request=None) -> "SiteConfiguration":
        """
        Return the current site configuration based on the SITE_ID in the
        project's settings. If SITE_ID isn't defined, return the site
        configuration matching ``request.site``.

        The ``SiteConfiguration`` object is cached the
        first time it's retrieved from the database.
        """
        if getattr(settings, 'SITE_ID', None):
            site_id = settings.SITE_ID
        elif request:
            site_id = request.site.pk
        else:
            raise ImproperlyConfigured(
                "Set the SITE_ID setting or pass a request to "
                "SiteConfiguration.objects.get_current() to fix this error."
            )
        return self.get_by_site_id(site_id)

    @staticmethod
    def clear_cache() -> None:
        """Clear the ``SiteConfiguration`` object cache."""
        global SITE_CONFIGURATION_CACHE
        SITE_CONFIGURATION_CACHE = {}

    def get_by_natural_key(self, domain: str) -> "SiteConfiguration":
        return self.get(site__domain=domain)


class SiteConfiguration(ConfigurationModel):
    site = models.OneToOneField(
        Site,
        verbose_name="Site",
        on_delete=models.CASCADE,
        related_name='site_configuration')
    default_from_email = models.CharField(
        "Default Email Address",
        max_length=255)
    email_backend = models.CharField(
        "Email Backend",
        help_text="Python import path of the backend to use for sending emails",
        max_length=255)
    # TODO: move stmp settings to JSONField
    email_host = models.CharField(
        "Email Host",
        help_text="The host of the SMTP server to use for sending email",
        max_length=255,
        blank=True)
    email_host_password = models.CharField(
        "Email Host Password",
        help_text="Password to use for the SMTP server defined in EMAIL_HOST. "
                  "Should be encrypted with a symmetric key stored in a "
                  "settings.SECRET_KEY",
        max_length=255,
        blank=True)
    email_host_user = models.CharField(
        "Email Host User",
        help_text="Username to use for the SMTP server defined in EMAIL_HOST",
        max_length=255,
        blank=True)
    email_port = models.PositiveSmallIntegerField(
        "Email Port",
        help_text="Port to use for the SMTP server defined in EMAIL_HOST.",
        blank=True,
        null=True)
    email_use_tls = models.BooleanField(
        "Use TLS",
        help_text="Whether to use an explicit TLS (secure) connection when "
                  "talking to the SMTP server",
        null=True)
    email_use_ssl = models.BooleanField(
        "Use SSL",
        help_text="Whether to use an implicit TLS (secure) connection when "
                  "talking to the SMTP server.",
        null=True)
    default_branch_code = models.CharField(
        "Branch code",
        max_length=10)
    instagram_access_token = models.CharField(
        max_length=420,
        blank=True, null=True)

    objects = SiteConfigurationManager()

    class Meta:
        verbose_name = "Site Configuration"
        db_table = "site_configurations"

    def __str__(self) -> str:
        return f"[SiteConfiguration] site: {self.site_id} domain: {self.site}"

    @classmethod
    def _get_fernet_key(cls):
        """Fernet key must be 32 url-safe base64-encoded bytes"""
        key = force_bytes(settings.DB_SECRET_KEY)[:32]
        return urlsafe_b64encode(key.ljust(32, b"="))

    @classmethod
    def encrypt(cls, value) -> str:
        f = Fernet(cls._get_fernet_key())
        return force_str(f.encrypt(force_bytes(value)))

    @classmethod
    def decrypt(cls, value) -> str:
        f = Fernet(cls._get_fernet_key())
        return force_str(f.decrypt(force_bytes(value)))


class City(TimezoneAwareMixin, models.Model):
    TIMEZONE_AWARE_FIELD_NAME = "time_zone"

    code = models.CharField(
        _("Code"),
        max_length=6,
        primary_key=True)
    name = models.CharField(_("City name"), max_length=255)
    abbr = models.CharField(_("Abbreviation"), max_length=20)
    time_zone = TimeZoneField(verbose_name=_("Timezone"))

    class Meta:
        ordering = ["name"]
        verbose_name = _("City")
        verbose_name_plural = _("Cities")

    def __str__(self):
        return smart_str(self.name)


# Used in migrations, can't be removed
class BranchManager(models.Manager):
    pass


class Location(TimezoneAwareMixin, models.Model):
    TIMEZONE_AWARE_FIELD_NAME = 'city'

    INTERVIEW = 'interview'
    LECTURE = 'lecture'
    UNSPECIFIED = 0  # BitField uses BigIntegerField internal

    city = models.ForeignKey(City,
                             verbose_name=_("City"),
                             default=settings.DEFAULT_CITY_CODE,
                             on_delete=models.PROTECT)
    name = models.CharField(_("Location|Name"), max_length=140)
    address = models.CharField(
        _("Address"),
        help_text=(_("Should be resolvable by Google Maps")),
        max_length=500,
        blank=True)
    description = models.TextField(
        _("Description"),
        help_text=LATEX_MARKDOWN_HTML_ENABLED)
    directions = models.TextField(
        _("Directions"),
        blank=True,
        null=True)
    flags = BitField(
        verbose_name=_("Flags"),
        flags=(
            (LECTURE, _('Class')),
            (INTERVIEW, _('Interview')),
        ),
        default=(LECTURE,),
        help_text=(_("Set purpose of this place")))

    class Meta:
        ordering = ("name",)
        verbose_name = _("Location|Name")
        verbose_name_plural = _("Locations")

    def __str__(self):
        return "{0}".format(smart_str(self.name))

    def get_absolute_url(self):
        return reverse('courses:venue_detail', args=[self.pk])


class University(models.Model):
    name = models.CharField(_("Name"), max_length=255)
    abbr = models.CharField(_("Abbreviation"), max_length=100,
                            blank=True, null=True)
    city = models.ForeignKey(City,
                             verbose_name=_("City"),
                             related_name="+",
                             null=True,
                             blank=True,
                             on_delete=models.PROTECT)

    class Meta:
        verbose_name = _("University")
        verbose_name_plural = _("Universities")

    def __str__(self):
        return self.name


class AcademicProgram(models.Model):
    title = models.TextField(_("Title"))
    code = models.TextField(_("Code"))

    university = models.ForeignKey(University,
                                   verbose_name=_("University"),
                                   related_name="programs",
                                   on_delete=models.PROTECT)

    class Meta:
        verbose_name = _("AcademicProgram")
        verbose_name_plural = _("AcademicPrograms")

    def __str__(self):
        return self.title

    def __repr__(self):
        return f"[AcademicProgram] id: {self.pk} code: {self.code}"


class AcademicProgramRun(models.Model):
    start_year = models.PositiveIntegerField(_('StartYear'))
    program = models.ForeignKey(AcademicProgram,
                                verbose_name=_("Program"),
                                related_name="runs",
                                on_delete=models.PROTECT)

    class Meta:
        verbose_name = _("AcademicProgramRun")
        verbose_name_plural = _("AcademicProgramRuns")

    def __str__(self):
        return f"{self.program.code} {self.start_year}"

    def __repr__(self):
        return f"[AcademicProgramRun] id: {self.pk} code: {self.program.code} year: {self.start_year}"


class TimestampedModel(models.Model):
    """
    Slightly modified version of model_utils.models.TimeStampedModel
    """
    created_at = AutoCreatedField(_('created'))
    modified_at = AutoLastModifiedField(_('modified'))

    def save(self, *args, **kwargs):
        """
        Overriding the save method in order to make sure that
        modified field is updated even if it is not given as
        a parameter to the update field argument.
        """
        update_fields = kwargs.get('update_fields', None)
        if update_fields:
            kwargs['update_fields'] = set(update_fields).union({'modified_at'})
        super().save(*args, **kwargs)

    class Meta:
        abstract = True


class Config(models.Model):
    alumni_chat_link = models.CharField(
        _('Alumni chat link'),
        blank=True,
    )

    class Meta:
        verbose_name = _('Config')
        verbose_name_plural = _('Config')
        constraints = [
            models.CheckConstraint(
                check=models.Q(id=1),
                name='config_unique',
            )
        ]

    @classmethod
    def get(cls) -> 'Config':
        try:
            return cls.objects.get(id=1)
        except cls.DoesNotExist:
            config = cls(id=1)
            config.save()
            return config

    def __str__(self):
        return 'Config'
