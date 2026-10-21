"""Presentation and native POST regression guards; no tax policy changes."""
from django.test import TestCase

from catalog.models import Product, Tax
from catalog.tests import test_product_related_continuation_cat012e_red as continuation
from people.tests.person_ui_support import Document


class ProductFormUXTests(TestCase):
    def setUp(self):
        continuation.ProductRelatedContinuationRedTests.setUp(self)

    authorize = continuation.ProductRelatedContinuationRedTests.authorize
    context = continuation.ProductRelatedContinuationRedTests.context
    parent_url = continuation.ProductRelatedContinuationRedTests.parent_url
    payload = continuation.ProductRelatedContinuationRedTests.payload
    isolated_case = continuation.ProductRelatedContinuationRedTests.isolated_case

    def test_secondary_refresh_follows_group_before_subgroup_in_create_and_edit(self):
        for editing in (False, True):
            with self.subTest(editing=editing):
                response = self.client.get(self.parent_url(editing))
                self.assertEqual(response.status_code, 200)
                doc = Document(response.content.decode())
                group = doc.matching('select', name='group')[0]
                subgroup = doc.matching('select', name='subgroup')[0]
                refresh = doc.matching('button', name='action', value='refresh_group')
                self.assertEqual(len(refresh), 1)
                refresh = refresh[0]
                self.assertLess(doc.nodes.index(group), doc.nodes.index(refresh))
                self.assertLess(doc.nodes.index(refresh), doc.nodes.index(subgroup))
                self.assertEqual(refresh.text, 'Actualizar subgrupos del grupo seleccionado')
                self.assertEqual(refresh.attrs['aria-label'], refresh.text)
                self.assertIn('secondary', refresh.attrs['class'].split())
                self.assertIn('formnovalidate', refresh.attrs)
                self.assertEqual(refresh.attrs['type'], 'submit')
                self.assertTrue(doc.matching('input', name='csrfmiddlewaretoken'))
                save = [n for n in doc.matching('button') if n.text.strip() == 'Guardar'][0]
                self.assertGreater(doc.nodes.index(save), doc.nodes.index(subgroup))

    def test_spanish_labels_and_native_tax_checkboxes_describe_real_options(self):
        response = self.client.get(self.parent_url(True))
        form = response.context['form']
        expected = {'code':'Código','barcode':'Código de barras','name':'Nombre',
                    'description':'Descripción','group':'Grupo','subgroup':'Subgrupo',
                    'brand':'Marca','unit_measure':'Unidad de medida',
                    'taxes':'Impuestos específicos del producto','cost_price':'Precio de costo',
                    'sale_price':'Precio de venta','is_service':'Es servicio',
                    'stock_control':'Control de existencias'}
        self.assertEqual({name:form[name].label for name in form.fields}, expected)
        doc = Document(response.content.decode())
        boxes = doc.matching('input', name='taxes', type='checkbox')
        self.assertEqual({b.attrs['value'] for b in boxes}, {str(self.iva.pk),str(self.ice.pk)})
        for box in boxes:
            self.assertIn('checked', box.attrs)
            labels = doc.matching('label', **{'for':box.attrs['id']})
            self.assertEqual(len(labels),1)
            tax = Tax.objects.get(pk=box.attrs['value'])
            self.assertIn(str(tax), labels[0].text)
        self.assertTrue([n for n in doc.matching('legend') if n.text == expected['taxes']])

    def test_no_eligible_taxes_has_human_empty_state_and_no_tax_actions(self):
        self.product.taxes.clear()
        Tax.objects.filter(company=self.company).update(is_active=False)
        for editing in (False, True):
            with self.subTest(editing=editing):
                response = self.client.get(self.parent_url(editing))
                self.assertContains(response,'No hay impuestos disponibles para seleccionar')
                doc = Document(response.content.decode())
                self.assertFalse(doc.matching('input',name='taxes'))
                self.assertFalse([n for n in doc.nodes if n.attrs.get('aria-label') in
                                  ('Adicionar impuesto','Consultar impuesto')])

    def test_refresh_preserves_draft_and_multiple_or_cleared_taxes_without_writes(self):
        for editing in (False, True):
            for taxes in ([str(self.iva.pk),str(self.ice.pk)], []):
                with self.subTest(editing=editing,taxes=taxes):
                    before = list(Product.objects.values())
                    before_taxes = list(Product.taxes.through.objects.values())
                    data = self.payload(taxes=taxes,code='',sale_price='valor inválido',stock_control='')
                    response = self.client.post(self.parent_url(editing),data|{'action':'refresh_group'})
                    self.assertEqual(response.status_code,200)
                    form = response.context['form']
                    for name in ('code','name','description','barcode','cost_price','sale_price',
                                 'group','subgroup','brand','unit_measure'):
                        self.assertEqual(str(form[name].value() or ''),str(data.get(name,'')))
                    self.assertEqual(sorted(map(str,form['taxes'].value() or [])),sorted(taxes))
                    self.assertFalse(form['stock_control'].value())
                    self.assertTrue(form['is_service'].value())
                    self.assertEqual(list(Product.objects.values()),before)
                    self.assertEqual(list(Product.taxes.through.objects.values()),before_taxes)
