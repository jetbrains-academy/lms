# -*- coding: utf-8 -*-
from datetime import datetime
from zoneinfo import ZoneInfo

import factory
from django.conf import settings
from django.contrib.sites.models import Site

from core.models import City, Location, SiteConfiguration, University, AcademicProgram, AcademicProgramRun
from core.tests.settings import TEST_DOMAIN

__all__ = ('CityFactory',
           'SiteFactory', 'LocationFactory', 'Location', 'Site', 'City')


class SiteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Site
        django_get_or_create = ('domain',)

    domain = TEST_DOMAIN
    name = factory.Sequence(lambda n: "Site Name %03d" % n)
    # TODO: create default site configuration


class SiteConfigurationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SiteConfiguration
        django_get_or_create = ('site',)

    site = factory.SubFactory(SiteFactory)
    enabled = True
    default_branch_code = 'spb'
    default_from_email = 'noreply@example.com'
    email_backend = settings.EMAIL_BACKEND
    email_host = settings.EMAIL_HOST
    email_host_password = SiteConfiguration.encrypt('password')
    email_host_user = factory.Sequence(lambda n: "User_%03d" % n)
    email_port = settings.EMAIL_PORT
    email_use_tls = False
    email_use_ssl = False


class CityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = City
        django_get_or_create = ('code',)

    code = factory.Sequence(lambda n: "%03d" % n)
    name = factory.Sequence(lambda n: "City name %03d" % n)
    abbr = factory.Sequence(lambda n: "%03d" % n)
    time_zone = ZoneInfo('Europe/Berlin')


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    city = factory.SubFactory(CityFactory)
    name = factory.Sequence(lambda n: "Location %03d" % n)
    description = factory.Sequence(lambda n: "location for tests %03d" % n)


class LegacyUniversityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = University

    name = factory.Sequence(lambda n: "University %03d" % n)
    city = factory.SubFactory(CityFactory)


class AcademicProgramFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AcademicProgram
        django_get_or_create = ('code',)

    title = factory.Sequence(lambda n: f'Program {n:03}')
    code = factory.Sequence(lambda n: f'PRG-{n:03}')
    university = factory.SubFactory(LegacyUniversityFactory)


class AcademicProgramRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AcademicProgramRun

    start_year = datetime.now().year
    program = factory.SubFactory(AcademicProgramFactory)
