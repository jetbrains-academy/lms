import pytest

from core.tests.settings import ANOTHER_DOMAIN, TEST_DOMAIN, TEST_DOMAIN_ID
from info_blocks.models import InfoBlock
from info_blocks.tests.factories import InfoBlockFactory, InfoBlockTagFactory


@pytest.mark.django_db
def test_info_blocks_manager_with_tag():
    tag1 = InfoBlockTagFactory(name="Useful")
    tag2 = InfoBlockTagFactory(name="Honor Code")
    u1, u2 = InfoBlockFactory.create_batch(2, tags=[tag1])
    u3 = InfoBlockFactory(tags=[tag2])

    infoblocks_useful = list(InfoBlock.objects.with_tag(tag1.slug))
    assert len(infoblocks_useful) == 2
    assert u1 in infoblocks_useful
    assert u2 in infoblocks_useful
