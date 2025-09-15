from io import BytesIO
from urllib.parse import urlparse

import pytest
from PIL import Image
from pytest_django.lazy_django import skip_if_no_django

from django.contrib.sites.models import Site
from django.core.files import File
from django.test import TestCase
from django.urls import resolve

from core.models import SiteConfiguration
from core.tests.factories import (
    CityFactory, SiteConfigurationFactory, SiteFactory
)
# noinspection PyUnresolvedReferences
from core.tests.fixtures import (
    university_cub, program_cub001, program_run_cub,
    university_nup, program_nup001, program_run_nup
)
from core.tests.settings import (
    ANOTHER_DOMAIN, ANOTHER_DOMAIN_ID, TEST_DOMAIN, TEST_DOMAIN_ID
)
from core.tests.utils import TestClient
from courses.models import CourseProgramBinding, Course, MetaCourse
from notifications.models import Type
from users.tests.factories import CuratorFactory


@pytest.fixture()
def client():
    """Customize login method for Django test client."""
    skip_if_no_django()
    return TestClient()


@pytest.fixture(scope="session")
def assert_redirect():
    """Uses customized TestCase.assertRedirects as a comparing tool."""
    _TC = TestCase()

    def wrapper(*args, **kwargs):
        # `fetch_redirect_response` will be broken if `expected_url` has an
        # absolute path since testing client always returns relative path
        # for the `response.url` (see `assertRedirects` for details)
        kwargs['fetch_redirect_response'] = False
        return _TC.assertRedirects(*args, **kwargs)

    return wrapper


@pytest.fixture(scope="function")
def assert_login_redirect(client, settings, assert_redirect):
    def wrapper(url, form=None, **kwargs):
        method_name = kwargs.pop("method", "get")
        client_method = getattr(client, method_name)
        # Cast `next` value to the relative path since
        # after successful login we redirect to the same domain.
        path = urlparse(url).path
        expected_path = "{}?next={}".format(settings.LOGIN_URL, path)
        assert_redirect(client_method(url, form, **kwargs), expected_path)

    return wrapper


@pytest.fixture(scope="function")
def curator():
    # Sequences are resetting for each test, don't rely on there values here
    return CuratorFactory(email='curators@test.ru',
                          first_name='Global',
                          username='curator',
                          last_name='Curator')


@pytest.fixture(scope="session")
def get_test_image():
    def wrapper(name='test.png', size=(50, 50), color=(256, 0, 0)):
        file_obj = BytesIO()
        _, ext = name.rsplit(".", maxsplit=1)
        image = Image.new("RGBA", size=size, color=color)
        image.save(file_obj, ext)
        file_obj.seek(0)
        return File(file_obj, name=name)

    return wrapper


@pytest.fixture(scope="function")
def lms_resolver():
    def wrapper(url):
        rel_url = urlparse(url).path
        lms_urlconf = 'lms.urls'
        return resolve(rel_url, urlconf=lms_urlconf)

    return wrapper


@pytest.fixture(scope="session", autouse=True)
def _prepopulate_db_with_data(django_db_setup, django_db_blocker):
    """
    Populates test database with missing data required for tests.

    To simplify db management migrations could be recreated from the scratch
    without already applied data migrations. Restore these data in one place
    since some tests rely on it.
    """
    with django_db_blocker.unblock():
        CourseProgramBinding.objects.all().delete()
        Course.objects.all().delete()
        MetaCourse.objects.all().delete()
        # Create site objects with respect to AutoField
        SiteConfiguration.objects.all().delete()
        Site.objects.all().delete()
        domains = [
            (TEST_DOMAIN_ID, TEST_DOMAIN),
            (ANOTHER_DOMAIN_ID, ANOTHER_DOMAIN),
        ]
        for site_id, domain in domains:
            Site.objects.update_or_create(id=site_id, defaults={
                "domain": domain,
                "name": domain
            })
        from django.core.management.color import no_style
        from django.db import connection
        sequence_sql = connection.ops.sequence_reset_sql(no_style(), [Site])
        with connection.cursor() as cursor:
            for sql in sequence_sql:
                cursor.execute(sql)
        # Model-based configuration
        site1 = SiteFactory(domain=TEST_DOMAIN)
        site1_conf = SiteConfigurationFactory(site=site1)
        site2 = SiteFactory(domain=ANOTHER_DOMAIN)
        site2_conf = SiteConfigurationFactory(site=site2)
        site2_conf.save()

        # Create cities
        from notifications import NotificationTypes
        for t in NotificationTypes:
            Type.objects.update_or_create(
                id=t.value,
                defaults={
                    "code": t.name
                }
            )
