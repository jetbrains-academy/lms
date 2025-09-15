from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework.filters import SearchFilter
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from users.api.serializers import CitySerializer, CountrySerializer
from users.models import City, Country
from users.tasks import send_new_city_email


class CountryViewSet(ReadOnlyModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    filter_backends = [SearchFilter]
    search_fields = ['name']


class CityViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = City.objects.all()
    serializer_class = CitySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['country_id']
    search_fields = ['name']

    def perform_create(self, serializer: CitySerializer):
        super().perform_create(serializer)
        send_new_city_email.delay(serializer.data['id'])
