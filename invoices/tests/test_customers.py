from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from django.urls import reverse

from invoices.models import Company, Customer, Invoice, Issuer, Project
from tests.support import AuthenticatedCompanyTestCase


class CustomerViewsTests(AuthenticatedCompanyTestCase):
    def setUp(self):
        self.today = timezone.localdate()
        issuer_company = Company.objects.create(name='Issuer Labs', customer_information_file_number='VATISS')
        self.issuer = Issuer.objects.create(company=issuer_company)

        client_company = Company.objects.create(name='Client Umbra', customer_information_file_number='VATC1')
        self.customer = Customer.objects.create(issuer=self.issuer, company=client_company)

        self.project_paid = Project.objects.create(customer=self.customer, title='Paid Work', project_code='PAID1')
        self.project_pending = Project.objects.create(customer=self.customer, title='Website Retainer', project_code='RETN1')

        self.paid_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project_paid,
            status=Invoice.STATUS_PAID,
            issued_date=self.today - timedelta(days=30),
            due_date=self.today - timedelta(days=15),
            total_due=Decimal('100'),
            amount_paid=Decimal('100'),
        )
        self.invoiced_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project_pending,
            status=Invoice.STATUS_INVOICED,
            issued_date=self.today - timedelta(days=10),
            due_date=self.today + timedelta(days=7),
            total_due=Decimal('200'),
            amount_due=Decimal('200'),
        )
        self.overdue_invoice = Invoice.objects.create(
            issuer=self.issuer,
            customer=self.customer,
            project=self.project_pending,
            status=Invoice.STATUS_OVERDUE,
            issued_date=self.today - timedelta(days=5),
            due_date=self.today - timedelta(days=1),
            total_due=Decimal('50'),
            amount_due=Decimal('50'),
            amount_overdue=Decimal('50'),
        )
        Invoice.objects.filter(pk=self.overdue_invoice.pk).update(
            status=Invoice.STATUS_INVOICED,
            amount_overdue=Decimal('0'),
        )
        self.overdue_invoice.refresh_from_db()

        base_time = timezone.now().replace(microsecond=0)
        Invoice.objects.filter(pk=self.paid_invoice.pk).update(updated_at=base_time - timedelta(days=3))
        Invoice.objects.filter(pk=self.invoiced_invoice.pk).update(updated_at=base_time - timedelta(days=1))
        Invoice.objects.filter(pk=self.overdue_invoice.pk).update(updated_at=base_time)
        self.latest_update = base_time

        self.user = self.create_user_with_issuers(
            [self.issuer],
            username='customer-views-user',
            email='customers@example.com',
        )
        self.client.force_login(self.user)

    def _activate_company(self):
        self.set_active_company(issuer=self.issuer)

    def test_customer_list_annotations(self):
        self._activate_company()

        response = self.client.get(reverse('customers:list'))
        self.assertEqual(response.status_code, 200)

        customers = list(response.context['customer_list'])
        self.assertEqual(len(customers), 1)
        annotated_customer = customers[0]

        self.assertEqual(annotated_customer.pk, self.customer.pk)
        self.assertEqual(annotated_customer.projects_count, 2)
        self.assertEqual(annotated_customer.paid_total, Decimal('100'))
        self.assertEqual(annotated_customer.pending_total, Decimal('250'))
        self.assertEqual(annotated_customer.overdue_total, Decimal('50'))
        self.assertEqual(annotated_customer.last_activity, self.overdue_invoice.issued_date)

    def test_customer_list_status_filters(self):
        self._activate_company()

        self.customer.is_active = False
        self.customer.save(update_fields=['is_active'])

        response_active = self.client.get(reverse('customers:list'))
        self.assertEqual(list(response_active.context['customer_list']), [])

        response_inactive = self.client.get(reverse('customers:list'), {'status': 'inactive'})
        inactive_customers = list(response_inactive.context['customer_list'])
        self.assertEqual(len(inactive_customers), 1)
        self.assertEqual(inactive_customers[0].pk, self.customer.pk)

    def test_customer_profile_context_totals(self):
        self._activate_company()

        response = self.client.get(reverse('customers:detail', args=[self.customer.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import expense statement')
        self.assertContains(response, reverse('expenses:csv_import'))

        invoice_totals = response.context['invoice_totals']
        self.assertEqual(invoice_totals['invoiced_total'], Decimal('350'))
        self.assertEqual(invoice_totals['pending_total'], Decimal('250'))
        self.assertEqual(invoice_totals['overdue_total'], Decimal('50'))

        projects = {project.pk: project for project in response.context['projects']}
        self.assertIn(self.project_paid.pk, projects)
        self.assertIn(self.project_pending.pk, projects)

        paid_project = projects[self.project_paid.pk]
        self.assertEqual(paid_project.invoiced_total, Decimal('100'))
        self.assertEqual(paid_project.paid_total, Decimal('100'))
        self.assertEqual(paid_project.pending_total, Decimal('0'))
        self.assertEqual(paid_project.overdue_total, Decimal('0'))

        pending_project = projects[self.project_pending.pk]
        self.assertEqual(pending_project.invoiced_total, Decimal('250'))
        self.assertEqual(pending_project.paid_total, Decimal('0'))
        self.assertEqual(pending_project.pending_total, Decimal('250'))
        self.assertEqual(pending_project.overdue_total, Decimal('50'))

    def test_customer_activity_distinguishes_unpaid_and_overdue_amounts(self):
        self._activate_company()

        response = self.client.get(reverse('customers:detail', args=[self.customer.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'account-table__amount-note--current', count=1)
        self.assertContains(response, 'account-table__amount-note--danger', count=1)
        self.assertContains(response, '(200.00 €)')
        self.assertContains(response, '(50.00 €)')

    def test_customer_order_preference_persisted(self):
        self._activate_company()

        other_company = Company.objects.create(name='Client Apex', customer_information_file_number='VATC2')
        other_customer = Customer.objects.create(issuer=self.issuer, company=other_company)
        other_project = Project.objects.create(customer=other_customer, title='Consulting', project_code='CONS1')

        Invoice.objects.create(
            issuer=self.issuer,
            customer=other_customer,
            project=other_project,
            status=Invoice.STATUS_INVOICED,
            issued_date=date(2024, 4, 10),
            total_due=Decimal('500'),
            amount_due=Decimal('500'),
        )

        response = self.client.get(reverse('customers:list'), {'order': 'pending_desc', 'date_range': 'all'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['order_filter'], 'pending_desc')
        self.assertEqual(self.client.session.get('customers_order'), 'pending_desc')

        follow_up = self.client.get(reverse('customers:list'), {'date_range': 'all'})
        self.assertEqual(follow_up.context['order_filter'], 'pending_desc')

        customers = list(follow_up.context['customer_list'])
        self.assertGreaterEqual(len(customers), 2)
        self.assertEqual(customers[0].pk, other_customer.pk)

    def test_customer_profile_edit_saves_payment_notes(self):
        self._activate_company()

        response = self.client.post(
            reverse('customers:detail', args=[self.customer.id]),
            {
                'tab': 'edit',
                'company-name': 'Client Umbra Updated',
                'company-customer_information_file_number': 'VATC1',
                'company-contact_name': 'Avery Client',
                'company-contact_email': 'avery@example.com',
                'company-contact_cc_email': '',
                'company-contact_phone_number': '',
                'company-contact_country': '',
                'address-full_address': '10 Client Street',
                'customer_status-is_active': 'true',
                'customer-currency': '',
                'customer-payment_term': '',
                'customer-payment_notes': 'Use local bank transfer details for this customer.',
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('customers:detail', args=[self.customer.id])}?tab=edit",
        )
        self.customer.refresh_from_db()
        self.assertEqual(
            self.customer.payment_notes,
            'Use local bank transfer details for this customer.',
        )

        follow_up = self.client.get(
            reverse('customers:detail', args=[self.customer.id]),
            {'tab': 'edit'},
        )
        self.assertContains(follow_up, 'Payment notes')
        self.assertContains(follow_up, 'Use local bank transfer details for this customer.')
