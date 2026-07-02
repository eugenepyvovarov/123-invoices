from django.db import transaction
from rest_framework import serializers
from rest_framework.reverse import reverse

from api.scoping import accessible_issuers_for_user, validate_writable_issuer
from invoices.models import Company, Customer, Invoice, Issuer, IssuerBankAccount, OrderLine, Project
from invoices.services.cached_totals import recalc_invoice_amounts


class AccountSerializer(serializers.Serializer):
    id = serializers.IntegerField(source='pk')
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    is_superuser = serializers.BooleanField()


class ApiUrlMixin:
    def get_url(self, obj):
        request = self.context.get('request')
        view_name = getattr(self.Meta, 'view_name', None)
        if request is None or view_name is None:
            return None
        return request.build_absolute_uri(reverse(view_name, args=[obj.pk]))


class CompanySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', read_only=True)
    address = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'address', 'bank_account_number', 'payment_method',
            'payment_terms', 'contact_name', 'contact_email', 'contact_cc_email',
            'contact_phone_number', 'contact_country',
        ]
        read_only_fields = fields


class BankAccountSerializer(ApiUrlMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', read_only=True)
    issuer_id = serializers.IntegerField(read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = IssuerBankAccount
        view_name = 'api:bankaccount-detail'
        fields = [
            'id', 'url', 'issuer_id', 'label', 'payment_method', 'account_details',
            'is_default', 'is_active', 'sort_order', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class IssuerSerializer(ApiUrlMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', read_only=True)
    company = CompanySerializer(read_only=True)
    bank_accounts = BankAccountSerializer(many=True, read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = Issuer
        view_name = 'api:issuer-detail'
        fields = [
            'id', 'url', 'company', 'invoice_format', 'next_invoice_number', 'bank_accounts',
        ]
        read_only_fields = fields


class CustomerSerializer(ApiUrlMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', read_only=True)
    url = serializers.SerializerMethodField()
    issuer_id = serializers.IntegerField(source='issuer.pk', read_only=True)
    issuer = serializers.PrimaryKeyRelatedField(queryset=Issuer.objects.none(), write_only=True)
    company = CompanySerializer(read_only=True)
    company_name = serializers.CharField(write_only=True, required=False, allow_blank=False)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    payment_term_name = serializers.CharField(source='payment_term.name', read_only=True)

    class Meta:
        model = Customer
        view_name = 'api:customer-detail'
        fields = [
            'id', 'url', 'external_id', 'issuer_id', 'issuer', 'company', 'company_name',
            'currency_code', 'payment_term_name', 'billing_email', 'billing_contact_name',
            'payment_notes', 'is_active',
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is not None:
            fields['issuer'].queryset = accessible_issuers_for_user(request.user)
        return fields

    def validate(self, attrs):
        request = self.context.get('request')
        issuer = attrs.get('issuer') or getattr(self.instance, 'issuer', None)
        if request is not None:
            validate_writable_issuer(request.user, issuer)
        return attrs

    def create(self, validated_data):
        company_name = validated_data.pop('company_name', None)
        if company_name:
            validated_data['company'] = Company.objects.create(name=company_name)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        company_name = validated_data.pop('company_name', None)
        if company_name:
            if instance.company_id:
                instance.company.name = company_name
                instance.company.save(update_fields=['name'])
            else:
                validated_data['company'] = Company.objects.create(name=company_name)
        return super().update(instance, validated_data)


class ProjectSerializer(ApiUrlMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', read_only=True)
    url = serializers.SerializerMethodField()
    issuer_id = serializers.IntegerField(source='issuer.pk', read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.none())
    customer_name = serializers.CharField(source='customer.company.name', read_only=True)
    payment_term_name = serializers.CharField(source='payment_term.name', read_only=True)

    class Meta:
        model = Project
        view_name = 'api:project-detail'
        fields = [
            'id', 'url', 'external_id', 'issuer_id', 'customer', 'customer_name',
            'title', 'status', 'project_code', 'comment', 'billing_reference',
            'payment_term_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['issuer_id', 'created_at', 'updated_at']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is not None:
            fields['customer'].queryset = Customer.objects.filter(
                issuer_id__in=accessible_issuers_for_user(request.user).values('id')
            ).select_related('company', 'issuer')
        return fields

    def validate(self, attrs):
        request = self.context.get('request')
        customer = attrs.get('customer') or getattr(self.instance, 'customer', None)
        if request is not None and customer is not None:
            validate_writable_issuer(request.user, customer.issuer)
        return attrs


class OrderLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='pk', required=False)

    class Meta:
        model = OrderLine
        fields = [
            'id', 'external_id', 'line_type', 'description', 'quantity', 'duration_seconds',
            'unit_price', 'line_total', 'manual_total', 'notes', 'time_entry_external_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class InvoiceSerializer(ApiUrlMixin, serializers.ModelSerializer):
    FINALIZED_STATUSES = {Invoice.STATUS_INVOICED, Invoice.STATUS_OVERDUE, Invoice.STATUS_PAID}

    id = serializers.IntegerField(source='pk', read_only=True)
    url = serializers.SerializerMethodField()
    issuer = serializers.PrimaryKeyRelatedField(queryset=Issuer.objects.none())
    issuer_id = serializers.IntegerField(source='issuer.pk', read_only=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.none())
    customer_name = serializers.CharField(source='customer.company.name', read_only=True)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.none(), required=False, allow_null=True)
    project_title = serializers.CharField(source='project.title', read_only=True)
    bank_account = serializers.PrimaryKeyRelatedField(
        queryset=IssuerBankAccount.objects.none(), required=False, allow_null=True
    )
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    order_lines = OrderLineSerializer(source='orderline_set', many=True, required=False)
    has_pdf = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        view_name = 'api:invoice-detail'
        fields = [
            'id', 'url', 'external_id', 'issuer', 'issuer_id', 'customer', 'customer_name',
            'project', 'project_title', 'bank_account', 'reference_number', 'status',
            'issued_date', 'due_date', 'sent_date', 'number', 'sequence', 'template_identifier',
            'comment', 'notes', 'currency_code', 'exchange_rate', 'discount_value',
            'discount_amount', 'tax_value', 'tax_base', 'tax_amount', 'secondary_tax_rate',
            'secondary_tax_name', 'uses_secondary_tax', 'sub_total', 'total_due',
            'base_currency_total', 'amount_paid', 'amount_due', 'amount_overdue',
            'last_payment_date', 'created_at', 'updated_at', 'has_pdf', 'pdf_url', 'order_lines',
        ]
        read_only_fields = [
            'status', 'number', 'discount_amount', 'tax_base', 'tax_amount', 'sub_total',
            'total_due', 'base_currency_total', 'amount_paid', 'amount_due', 'amount_overdue',
            'last_payment_date', 'created_at', 'updated_at', 'has_pdf', 'pdf_url',
        ]

    def get_has_pdf(self, obj):
        return bool(getattr(obj, 'pdf_document', None) and obj.pdf_document.name)

    def get_pdf_url(self, obj):
        request = self.context.get('request')
        if request is None or not self.get_has_pdf(obj):
            return None
        return request.build_absolute_uri(reverse('api:invoice-download-pdf', args=[obj.pk]))

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is not None:
            issuer_ids = accessible_issuers_for_user(request.user).values('id')
            fields['issuer'].queryset = Issuer.objects.filter(pk__in=issuer_ids)
            fields['customer'].queryset = Customer.objects.filter(issuer_id__in=issuer_ids).select_related('company')
            fields['project'].queryset = Project.objects.filter(issuer_id__in=issuer_ids).select_related('customer')
            fields['bank_account'].queryset = IssuerBankAccount.objects.filter(issuer_id__in=issuer_ids)
        return fields

    def validate(self, attrs):
        if self.instance and self.instance.status in self.FINALIZED_STATUSES:
            raise serializers.ValidationError('Finalized invoices cannot be changed through the API.')

        request = self.context.get('request')
        issuer = attrs.get('issuer') or getattr(self.instance, 'issuer', None)
        customer = attrs.get('customer') or getattr(self.instance, 'customer', None)
        project = attrs.get('project') if 'project' in attrs else getattr(self.instance, 'project', None)
        bank_account = attrs.get('bank_account') if 'bank_account' in attrs else getattr(self.instance, 'bank_account', None)

        if request is not None:
            validate_writable_issuer(request.user, issuer)
        if customer is not None and issuer is not None and customer.issuer_id != issuer.pk:
            raise serializers.ValidationError({'customer': 'Customer must belong to the invoice issuer.'})
        if project is not None:
            if customer is not None and project.customer_id != customer.pk:
                raise serializers.ValidationError({'project': 'Project must belong to the invoice customer.'})
            if issuer is not None and project.issuer_id != issuer.pk:
                raise serializers.ValidationError({'project': 'Project must belong to the invoice issuer.'})
        if bank_account is not None and issuer is not None and bank_account.issuer_id != issuer.pk:
            raise serializers.ValidationError({'bank_account': 'Bank account must belong to the invoice issuer.'})
        return attrs

    def _sync_order_lines(self, invoice, order_lines_data):
        if order_lines_data is None:
            return
        existing = {line.pk: line for line in invoice.orderline_set.all()}
        seen_ids = set()
        for line_data in order_lines_data:
            line_id = line_data.pop('pk', None)
            if line_id:
                line = existing.get(line_id)
                if line is None:
                    raise serializers.ValidationError({'order_lines': f'Order line {line_id} does not belong to this invoice.'})
                for field, value in line_data.items():
                    setattr(line, field, value)
                line.invoice = invoice
                line.save()
                seen_ids.add(line.pk)
            else:
                line = OrderLine.objects.create(invoice=invoice, **line_data)
                seen_ids.add(line.pk)
        for line_id, line in existing.items():
            if line_id not in seen_ids:
                line.delete()

    def _recalculate_invoice(self, invoice):
        invoice.calculate_totals(OrderLine.objects.filter(invoice=invoice))
        invoice.save()
        recalc_invoice_amounts(invoice.pk)

    @transaction.atomic
    def create(self, validated_data):
        order_lines_data = validated_data.pop('orderline_set', [])
        invoice = Invoice.objects.create(**validated_data)
        self._sync_order_lines(invoice, order_lines_data)
        self._recalculate_invoice(invoice)
        return invoice

    @transaction.atomic
    def update(self, instance, validated_data):
        order_lines_data = validated_data.pop('orderline_set', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        self._sync_order_lines(instance, order_lines_data)
        self._recalculate_invoice(instance)
        return instance
