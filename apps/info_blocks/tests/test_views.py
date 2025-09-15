import pytest

from django.urls import reverse

from info_blocks.tests.factories import InfoBlockTagFactory, InfoBlockFactory
from info_blocks.tests.utils import extract_tags_from_response
from users.tests.factories import CuratorFactory


@pytest.mark.django_db
def test_autocomplete_tags_should_be_sorted(client):
    curator = CuratorFactory()
    tag1 = InfoBlockTagFactory(name="zzz")
    tag2 = InfoBlockTagFactory(name="aaa")

    client.login(curator)
    response = client.get(reverse('admin:info_blocks_tags_autocomplete'))
    assert response.status_code == 200
    tags = extract_tags_from_response(response)
    # Tags should be sorted
    assert tags[0] == 'aaa'
    assert tags[1] == 'zzz'


@pytest.mark.django_db
def test_autocomplete_should_support_lookup(client):
    curator = CuratorFactory()
    tag1 = InfoBlockTagFactory(name="zzz")
    tag2 = InfoBlockTagFactory(name="aaa")

    client.login(curator)
    response = client.get(reverse('admin:info_blocks_tags_autocomplete'), {'q': 'a'})
    assert response.status_code == 200
    tags = extract_tags_from_response(response)
    assert ['aaa'] == tags


@pytest.mark.django_db
def test_infoblocks_page_works_properly(client, curator):
    url = reverse('admin:info_blocks_infoblock_changelist')
    client.login(curator)
    normal_infoblock = InfoBlockFactory(tags=['meow'])
    infoblock_with_no_tags = InfoBlockFactory()
    assert infoblock_with_no_tags.tags.count() == 0
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context_data['cl'].result_list.count() == 2
