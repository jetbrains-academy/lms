import pytest
from django.db import IntegrityError

from core.models import SiteConfiguration, Config
from core.tests.factories import SiteConfigurationFactory, SiteFactory


@pytest.mark.django_db
def test_manager_site_configuration_get_current(rf, settings):
    site1 = SiteFactory(domain='example1.org')
    site_configuration1 = SiteConfigurationFactory(site=site1)
    site2 = SiteFactory(domain='example2.org')
    site_configuration2 = SiteConfigurationFactory(site=site2)
    settings.SITE_ID = site2.pk
    request = rf.request()
    request.site = site1
    request.path = '/'
    assert SiteConfiguration.objects.get_current() == site_configuration2
    assert SiteConfiguration.objects.get_current(request) == site_configuration2
    settings.SITE_ID = None
    assert SiteConfiguration.objects.get_current(request) == site_configuration1


@pytest.mark.django_db
def test_model_site_configuration_encrypt_decrypt(rf, settings):
    settings.SECRET_KEY = 'short'
    value = 'secret_value'
    encrypted = SiteConfiguration.encrypt(value)
    assert SiteConfiguration.decrypt(encrypted) == value
    settings.SECRET_KEY = 'hesoHHp44vRYpd#6mX$jX>6k*ue$gZhmzEE>wcF]48U'
    assert len(settings.SECRET_KEY) > 32
    value = 'secret password'
    encrypted = SiteConfiguration.encrypt(value)
    assert SiteConfiguration.decrypt(encrypted) == value


@pytest.mark.django_db
def test_config():
    config = Config.get()
    assert config.id == 1
    # Should always return the same object
    config = Config.get()
    assert config.id == 1
    # Should not allow to create additional objects
    with pytest.raises(IntegrityError):
        Config(id=2).save()
