"""Regression guards for consumed nested continuations and a preserved outer draft."""
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from people.models.geography import Continent, Country


class RelatedContinuationSecurityTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_superuser('continuation-operator', password='test-only')
        self.client.force_login(self.actor)
        self.continent = Continent.objects.create(name='Initial continent')

    def token(self, response):
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlsplit(response['Location']).query)['draft'][0]

    def company_person(self):
        response = self.client.post(reverse('company_create'), {
            'commercial_name': 'Preserved outer draft', 'action': 'add_person',
        })
        return self.token(response)

    def person_country(self, token):
        return self.client.post(reverse('person_create'), {
            'draft': token, 'full_name': 'Preserved Person draft',
            'continent': self.continent.pk, 'related': 'add:country',
        })

    def test_consumed_nested_parent_rejects_replay_before_a_second_write(self):
        outer = self.company_person()
        country_token = self.token(self.person_country(outer))
        continent_token = self.token(self.client.post(reverse('country_create'), {
            'draft': country_token, 'continent': self.continent.pk,
            'code': 'NEW', 'name': 'Country draft', 'related': 'add:continent',
        }))
        self.token(self.client.post(reverse('continent_create'), {
            'draft': continent_token, 'name': 'Created continent',
        }))
        created = Continent.objects.get(name='Created continent')
        self.token(self.client.post(reverse('country_create'), {
            'draft': continent_token, 'continent': created.pk,
            'code': 'NEW', 'name': 'Created country',
        }))
        before = list(Country.objects.values())
        replay = self.client.post(reverse('country_create'), {
            'draft': continent_token, 'continent': created.pk,
            'code': 'REPLAY', 'name': 'Unauthorized second write',
        })
        self.assertEqual(replay.status_code, 403)
        self.assertEqual(list(Country.objects.values()), before)

    def test_repeated_related_returns_preserve_the_original_company_continuation(self):
        token = self.company_person()
        for _ in range(8):
            token = self.token(self.person_country(token))
            token = self.token(self.client.post(reverse('country_create'), {
                'draft': token, 'action': 'cancel',
            }))
        response = self.client.post(reverse('person_create'), {'draft': token, 'action': 'cancel'})
        self.assertEqual(response.status_code, 302)
        returned = self.client.get(response['Location'])
        self.assertContains(returned, 'Preserved outer draft')
        self.assertEqual(Country.objects.count(), 0)
