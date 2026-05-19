from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.urls import reverse

from invoices.forms import ProjectForm
from invoices.models import Company, Customer, Invoice, Issuer, Project
from tests.support import AuthenticatedCompanyTestCase


class ProjectFormTests(TestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        active_company = Company.objects.create(name='Active Client', customer_information_file_number='VATC1')
        self.active_customer = Customer.objects.create(issuer=self.issuer, company=active_company, is_active=True)

        inactive_company = Company.objects.create(name='Inactive Client', customer_information_file_number='VATC2')
        self.inactive_customer = Customer.objects.create(issuer=self.issuer, company=inactive_company, is_active=False)

        unrelated_inactive_company = Company.objects.create(
            name='Unrelated Inactive Client',
            customer_information_file_number='VATC5',
        )
        self.unrelated_inactive_customer = Customer.objects.create(
            issuer=self.issuer,
            company=unrelated_inactive_company,
            is_active=False,
        )

        other_issuer_company = Company.objects.create(name='Other Issuer', customer_information_file_number='VATOTH')
        self.other_issuer = Issuer.objects.create(company=other_issuer_company)
        other_company = Company.objects.create(name='Other Client', customer_information_file_number='VATC3')
        self.other_customer = Customer.objects.create(issuer=self.other_issuer, company=other_company, is_active=True)
        other_inactive_company = Company.objects.create(name='Other Inactive Client', customer_information_file_number='VATC4')
        self.other_inactive_customer = Customer.objects.create(
            issuer=self.other_issuer,
            company=other_inactive_company,
            is_active=False,
        )

    def test_new_project_form_lists_only_active_customers_for_issuer(self):
        form = ProjectForm(issuer=self.issuer)

        queryset = list(form.fields['customer'].queryset)

        self.assertEqual(queryset, [self.active_customer])

    def test_edit_project_form_includes_assigned_inactive_customer(self):
        project = Project.objects.create(
            customer=self.inactive_customer,
            title='Dormant Project',
            project_code='DORM1',
        )

        form = ProjectForm(instance=project, issuer=self.issuer)

        queryset = list(form.fields['customer'].queryset)
        customer_field_html = str(form['customer'])

        self.assertIn(self.active_customer, queryset)
        self.assertIn(self.inactive_customer, queryset)
        self.assertNotIn(self.unrelated_inactive_customer, queryset)
        self.assertNotIn(self.other_customer, queryset)
        self.assertNotIn(self.other_inactive_customer, queryset)
        self.assertEqual(form['customer'].value(), project.customer_id)
        self.assertIn(f'value="{self.inactive_customer.id}" selected', customer_field_html)
        self.assertIn('Inactive Client (inactive)', customer_field_html)

    def test_edit_project_form_does_not_expose_inactive_customer_from_other_issuer(self):
        project = Project.objects.create(
            customer=self.other_inactive_customer,
            title='Foreign Dormant Project',
            project_code='DORM3',
        )

        form = ProjectForm(instance=project, issuer=self.issuer)

        queryset = list(form.fields['customer'].queryset)

        self.assertEqual(queryset, [self.active_customer])

    def test_edit_project_form_labels_assigned_inactive_customer(self):
        project = Project.objects.create(
            customer=self.inactive_customer,
            title='Dormant Project',
            project_code='DORM2',
        )

        form = ProjectForm(instance=project, issuer=self.issuer)

        self.assertEqual(
            form.fields['customer'].label_from_instance(self.inactive_customer),
            'Inactive Client (inactive)',
        )
        self.assertEqual(
            form.fields['customer'].label_from_instance(self.active_customer),
            'Active Client',
        )

    def test_project_issuer_is_synchronized_from_customer(self):
        project = Project.objects.create(
            customer=self.active_customer,
            title='Scoped Project',
            project_code='SYNC1',
        )

        self.assertEqual(project.issuer, self.issuer)

        project.customer = self.other_customer
        project.save()
        project.refresh_from_db()

        self.assertEqual(project.issuer, self.other_issuer)

    def test_same_issuer_duplicate_project_codes_are_rejected_by_database(self):
        other_company = Company.objects.create(name='Second Client', customer_information_file_number='VATC6')
        other_customer = Customer.objects.create(issuer=self.issuer, company=other_company, is_active=True)
        Project.objects.create(customer=self.active_customer, title='First Project', project_code='DUP1')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Project.objects.create(customer=other_customer, title='Second Project', project_code='DUP1')

    def test_cross_issuer_duplicate_project_codes_are_allowed(self):
        Project.objects.create(customer=self.active_customer, title='First Project', project_code='SHARED1')
        project = Project.objects.create(
            customer=self.other_customer,
            title='Other Issuer Project',
            project_code='SHARED1',
        )

        self.assertEqual(project.issuer, self.other_issuer)

    def test_model_validation_rejects_same_issuer_duplicate_project_code(self):
        other_company = Company.objects.create(name='Second Client', customer_information_file_number='VATC6')
        other_customer = Customer.objects.create(issuer=self.issuer, company=other_company, is_active=True)
        Project.objects.create(customer=self.active_customer, title='First Project', project_code='DUP2')
        project = Project(customer=other_customer, title='Second Project', project_code='DUP2')

        with self.assertRaises(ValidationError) as context:
            project.full_clean()

        self.assertIn('project_code', context.exception.message_dict)

    def test_project_form_rejects_same_issuer_duplicate_project_code(self):
        other_company = Company.objects.create(name='Second Client', customer_information_file_number='VATC6')
        other_customer = Customer.objects.create(issuer=self.issuer, company=other_company, is_active=True)
        Project.objects.create(customer=self.active_customer, title='First Project', project_code='DUP3')

        form = ProjectForm(
            data={
                'project-title': 'Second Project',
                'project-project_code': 'DUP3',
                'project-status': Project.STATUS_ACTIVE,
                'project-customer': str(other_customer.pk),
                'project-payment_term': '',
                'project-comment': '',
            },
            issuer=self.issuer,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('project_code', form.errors)

    def test_project_form_allows_current_project_code_on_edit(self):
        project = Project.objects.create(
            customer=self.active_customer,
            title='Editable Project',
            project_code='EDIT1',
        )

        form = ProjectForm(
            data={
                'project-title': 'Edited Project',
                'project-project_code': 'EDIT1',
                'project-status': Project.STATUS_ACTIVE,
                'project-customer': str(self.active_customer.pk),
                'project-payment_term': '',
                'project-comment': '',
            },
            instance=project,
            issuer=self.issuer,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_project_form_rejects_edit_to_same_issuer_duplicate_project_code(self):
        other_company = Company.objects.create(name='Second Client', customer_information_file_number='VATC6')
        other_customer = Customer.objects.create(issuer=self.issuer, company=other_company, is_active=True)
        Project.objects.create(customer=self.active_customer, title='First Project', project_code='DUP4')
        project = Project.objects.create(
            customer=other_customer,
            title='Editable Project',
            project_code='EDIT2',
        )

        form = ProjectForm(
            data={
                'project-title': 'Edited Project',
                'project-project_code': 'DUP4',
                'project-status': Project.STATUS_ACTIVE,
                'project-customer': str(other_customer.pk),
                'project-payment_term': '',
                'project-comment': '',
            },
            instance=project,
            issuer=self.issuer,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('project_code', form.errors)


class ProjectEditViewTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        active_company = Company.objects.create(name='Active Client', customer_information_file_number='VATC1')
        self.active_customer = Customer.objects.create(issuer=self.issuer, company=active_company, is_active=True)

        inactive_company = Company.objects.create(name='Inactive Client', customer_information_file_number='VATC2')
        self.inactive_customer = Customer.objects.create(issuer=self.issuer, company=inactive_company, is_active=False)

        unrelated_inactive_company = Company.objects.create(
            name='Unrelated Inactive Client',
            customer_information_file_number='VATC3',
        )
        self.unrelated_inactive_customer = Customer.objects.create(
            issuer=self.issuer,
            company=unrelated_inactive_company,
            is_active=False,
        )

        self.project = Project.objects.create(
            customer=self.inactive_customer,
            title='Dormant Project',
            project_code='DORM1',
        )

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='project-edit-user',
            email='project-edit@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def test_standalone_edit_view_includes_assigned_inactive_customer(self):
        response = self.client.get(reverse('projects:edit', args=[self.project.id]))

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        queryset = list(form.fields['customer'].queryset)

        self.assertEqual(form['customer'].value(), self.inactive_customer.id)
        self.assertIn(self.active_customer, queryset)
        self.assertIn(self.inactive_customer, queryset)
        self.assertNotIn(self.unrelated_inactive_customer, queryset)
        self.assertContains(response, 'Inactive Client (inactive)')

    def test_project_detail_edit_tab_includes_assigned_inactive_customer(self):
        response = self.client.get(reverse('projects:detail', args=[self.project.id]), {'tab': 'edit'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_tab'], 'edit')
        self.assertContains(response, 'Import expense statement')
        self.assertContains(response, reverse('expenses:csv_import'))

        form = response.context['project_form']
        queryset = list(form.fields['customer'].queryset)

        self.assertEqual(form['customer'].value(), self.inactive_customer.id)
        self.assertIn(self.active_customer, queryset)
        self.assertIn(self.inactive_customer, queryset)
        self.assertNotIn(self.unrelated_inactive_customer, queryset)
        self.assertContains(response, 'Inactive Client (inactive)')

    def test_project_detail_edit_tab_updates_status_with_inactive_customer(self):
        response = self.client.post(
            reverse('projects:detail', args=[self.project.id]),
            data={
                'tab': 'edit',
                'project-title': self.project.title,
                'project-project_code': self.project.project_code,
                'project-status': Project.STATUS_INACTIVE,
                'project-customer': str(self.inactive_customer.id),
                'project-payment_term': '',
                'project-comment': '',
            },
        )

        self.assertRedirects(response, f"{reverse('projects:detail', args=[self.project.id])}?tab=edit")
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.STATUS_INACTIVE)
        self.assertEqual(self.project.customer, self.inactive_customer)

    def test_standalone_edit_view_updates_status_with_inactive_customer(self):
        response = self.client.post(
            reverse('projects:edit', args=[self.project.id]),
            data={
                'project-title': self.project.title,
                'project-project_code': self.project.project_code,
                'project-status': Project.STATUS_INACTIVE,
                'project-customer': str(self.inactive_customer.id),
                'project-payment_term': '',
                'project-comment': '',
            },
        )

        self.assertRedirects(response, reverse('projects:list'))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.STATUS_INACTIVE)
        self.assertEqual(self.project.customer, self.inactive_customer)


class ProjectCreationViewTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        issuer_company = Company.objects.create(name='Issuer', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        active_company = Company.objects.create(name='Active Client', customer_information_file_number='VATC1')
        self.active_customer = Customer.objects.create(issuer=self.issuer, company=active_company, is_active=True)

        inactive_company = Company.objects.create(name='Inactive Client', customer_information_file_number='VATC2')
        self.inactive_customer = Customer.objects.create(issuer=self.issuer, company=inactive_company, is_active=False)

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='project-create-user',
            email='project-create@example.com',
        )
        self.login_with_active_company(self.user, issuer=self.issuer)

    def test_add_project_view_excludes_inactive_customers(self):
        response = self.client.get(reverse('projects:add'))

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        queryset = list(form.fields['customer'].queryset)

        self.assertEqual(queryset, [self.active_customer])
        self.assertNotContains(response, 'Inactive Client (inactive)')
