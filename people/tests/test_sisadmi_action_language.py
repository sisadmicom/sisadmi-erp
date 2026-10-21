"""Human action names, authorized controls and safe catalog deletion."""
from django.contrib.staticfiles import finders
from people.models.geography import Continent
from people.tests.person_ui_support import PersonUIFixture


class SisadmiActionLanguageTests(PersonUIFixture):
    def test_person_actions_are_accessible_local_and_scoped(self):
        response = self.page('person_list')
        self.assertContains(response, 'aria-label="Adicionar persona"')
        self.assertContains(response, 'aria-label="Consultar persona"')
        self.assertContains(response, 'aria-label="Editar persona"')
        self.assertNotContains(response, self.hidden_person.identification)
        for kind in ('add', 'view', 'edit', 'delete'):
            self.assertIsNotNone(finders.find('core/icons/' + kind + '.svg'))
        self.restrict(self.actor, 'view_person')
        response = self.page('person_list')
        self.assertNotContains(response, 'aria-label="Adicionar persona"')
        self.assertNotContains(response, 'aria-label="Editar persona"')

    def test_relation_actions_remain_native_posts_with_specific_names(self):
        chain = self.chain()
        self.grant(self.actor, 'delete_continent')
        response = self.page('country_update', chain['country'])
        for label in ('Adicionar continente', 'Editar continente', 'Eliminar continente'):
            controls = self.doc(response).matching('button', **{'aria-label': label})
            self.assertEqual(len(controls), 1)
            self.assertEqual(controls[0].attrs['type'], 'submit')
            self.assertIn('formnovalidate', controls[0].attrs)

    def test_catalog_delete_visibility_and_dependency_protection(self):
        chain = self.chain()
        response = self.page('continent_list')
        self.assertNotContains(response, 'aria-label="Eliminar continente"')
        self.grant(self.actor, 'delete_continent')
        response = self.page('continent_list')
        self.assertContains(response, 'aria-label="Eliminar continente"')
        before = Continent.objects.count()
        self.page('continent_delete', chain['continent'])
        self.assertEqual(Continent.objects.count(), before)
        response = self.client.post(self.url('continent_delete', chain['continent']), {})
        self.assertContains(response, 'No se puede eliminar este continente porque está siendo utilizado.')
        self.assertTrue(Continent.objects.filter(pk=chain['continent'].pk).exists())
