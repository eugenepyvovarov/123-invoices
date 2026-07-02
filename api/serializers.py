from rest_framework import serializers
from rest_framework.reverse import reverse

from api.scoping import accessible_issuers_for_user, validate_writable_issuer
from invoices.models import Company, Customer, Issuer, IssuerBankAccount, Project


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
