from django.contrib import admin

from .models import (
    Address,
    Company,
    Currency,
    Customer,
    IncomingEmailSource,
    IncomingInvoiceArtifact,
    IncomingInvoiceCandidate,
    Invoice,
    IssuerEmailRoutingRule,
    IssuerBankAccount,
    Issuer,
    IssuerSifSettings,
    OrderLine,
    Payment,
    PaymentApplication,
    PaymentTerm,
    Project,
    Statement,
)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("alias", "full_address_short")
    search_fields = ("alias", "full_address", "street", "city", "country")

    @staticmethod
    def full_address_short(obj):
        full_address = obj.full_address or ""
        first_line = full_address.split("\n", 1)[0]
        return first_line[:60]

    full_address_short.short_description = "Address"


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "contact_name",
        "contact_email",
        "customer_information_file_number",
        "payment_term",
    )
    search_fields = ("name", "contact_name", "contact_email", "customer_information_file_number")
    autocomplete_fields = ("address", "payment_term")
    fieldsets = (
        (
            "Company",
            {
                "fields": (
                    "name",
                    "customer_information_file_number",
                    "logo",
                )
            },
        ),
        (
            "Primary contact",
            {
                "fields": (
                    "contact_name",
                    "contact_email",
                    "contact_cc_email",
                    "contact_phone_number",
                    "contact_country",
                )
            },
        ),
        (
            "Billing details",
            {
                "fields": (
                    "payment_method",
                    "payment_term",
                    "payment_terms",
                    "bank_account_number",
                )
            },
        ),
        ("Address", {"fields": ("address",)}),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "issuer",
        "billing_contact_name",
        "billing_email",
        "currency",
        "payment_term",
        "is_active",
    )
    list_filter = ("is_active", "issuer", "currency", "payment_term")
    search_fields = ("company__name", "billing_contact_name", "billing_email")
    autocomplete_fields = ("company", "issuer", "currency", "payment_term")


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    fields = ("description", "line_type", "quantity", "unit_price", "line_total")
    readonly_fields = ("line_total",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "reference_number",
        "issuer",
        "customer",
        "project",
        "status",
        "issued_date",
        "total_due",
        "currency",
        "bank_account",
    )
    search_fields = ("reference_number", "customer__company__name", "project__title")
    list_filter = ("status", "currency", "issuer", "bank_account")
    date_hierarchy = "issued_date"
    autocomplete_fields = ("issuer", "customer", "project", "currency", "bank_account")
    inlines = [OrderLineInline]


@admin.register(IssuerBankAccount)
class IssuerBankAccountAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "issuer",
        "payment_method",
        "is_default",
        "is_active",
        "sort_order",
    )
    list_filter = ("issuer", "is_default", "is_active")
    search_fields = ("label", "account_details", "issuer__company__name")
    autocomplete_fields = ("issuer",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "external_id",
        "issuer",
        "customer",
        "project",
        "amount",
        "status",
        "received_at",
    )
    list_filter = ("status", "issuer")
    search_fields = ("external_id", "customer__company__name", "memo")
    date_hierarchy = "received_at"
    autocomplete_fields = ("issuer", "customer", "project", "currency")


@admin.register(PaymentApplication)
class PaymentApplicationAdmin(admin.ModelAdmin):
    list_display = ("payment", "invoice", "amount_applied", "applied_at")
    autocomplete_fields = ("payment", "invoice")
    search_fields = ("payment__external_id", "invoice__reference_number")


@admin.register(PaymentTerm)
class PaymentTermAdmin(admin.ModelAdmin):
    list_display = ("name", "days", "description")
    search_fields = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_code", "title", "customer", "issuer", "status", "billing_reference")
    list_filter = ("status", "issuer")
    search_fields = ("project_code", "title", "customer__company__name", "issuer__company__name")
    autocomplete_fields = ("customer", "payment_term")


@admin.register(Issuer)
class IssuerAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "invoice_format", "next_invoice_number", "sif_tax_country", "sif_mode", "sif_readiness")
    search_fields = ("company__name",)
    autocomplete_fields = ("company",)

    @admin.display(description="SIF country")
    def sif_tax_country(self, obj):
        return getattr(getattr(obj, "sif_settings", None), "tax_country", "") or "—"

    @admin.display(description="SIF mode")
    def sif_mode(self, obj):
        settings = getattr(obj, "sif_settings", None)
        return settings.get_mode_display() if settings else "—"

    @admin.display(description="SIF readiness")
    def sif_readiness(self, obj):
        settings = getattr(obj, "sif_settings", None)
        if not settings:
            return "No settings"
        return f"{'Enabled' if settings.enabled else 'Disabled'} / {settings.get_operational_status_display()}"


@admin.register(IssuerSifSettings)
class IssuerSifSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "issuer",
        "tax_country",
        "enabled",
        "mode",
        "aeat_environment",
        "deadline_category",
        "informational_deadline",
        "operational_status",
    )
    list_filter = ("tax_country", "enabled", "mode", "aeat_environment", "deadline_category", "operational_status")
    search_fields = ("issuer__company__name", "issuer__company__customer_information_file_number", "certificate_reference")
    autocomplete_fields = ("issuer",)
    readonly_fields = ("created_at", "updated_at", "informational_deadline")
    fieldsets = (
        ("Issuer", {"fields": ("issuer", "tax_country", "enabled", "mode")}),
        ("AEAT and readiness", {"fields": ("aeat_environment", "taxpayer_role", "deadline_category", "informational_deadline", "operational_status")}),
        ("Software declaration", {"fields": ("software_name", "software_version", "software_code", "certificate_reference")}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "is_base")
    search_fields = ("code", "name")
    list_filter = ("is_base",)


class IncomingInvoiceArtifactInline(admin.TabularInline):
    model = IncomingInvoiceArtifact
    extra = 0
    fields = ("kind", "original_filename", "content_type", "size", "sha256", "is_invoice_like", "invoice_confidence")
    readonly_fields = ("size", "sha256")


@admin.register(IncomingEmailSource)
class IncomingEmailSourceAdmin(admin.ModelAdmin):
    list_display = ("display_name", "email_address", "provider", "issuer", "is_enabled", "last_seen_message_at")
    list_filter = ("provider", "is_enabled", "issuer")
    search_fields = ("display_name", "email_address", "folder", "polling_query")
    autocomplete_fields = ("issuer", "user")
    readonly_fields = ("created_at", "updated_at")


@admin.register(IssuerEmailRoutingRule)
class IssuerEmailRoutingRuleAdmin(admin.ModelAdmin):
    list_display = ("issuer", "auto_assign_enabled", "confidence_threshold", "alias_count", "keyword_count")
    list_filter = ("auto_assign_enabled",)
    search_fields = ("issuer__company__name",)
    autocomplete_fields = ("issuer",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Aliases")
    def alias_count(self, obj):
        return len(obj.recipient_aliases or []) + len(obj.delivered_to_addresses or [])

    @admin.display(description="Keywords")
    def keyword_count(self, obj):
        return len(obj.keywords or [])


@admin.register(IncomingInvoiceCandidate)
class IncomingInvoiceCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "display_subject",
        "status",
        "source",
        "suggested_issuer",
        "confirmed_issuer",
        "received_at",
        "artifact_count",
    )
    list_filter = ("status", "source", "suggested_issuer", "confirmed_issuer", "received_at")
    search_fields = ("subject", "provider_message_id", "from_name", "from_email")
    autocomplete_fields = (
        "source",
        "suggested_issuer",
        "confirmed_issuer",
        "selected_artifact",
        "generated_body_pdf_artifact",
        "converted_expense",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "received_at"
    inlines = [IncomingInvoiceArtifactInline]

    @admin.display(description="Artifacts")
    def artifact_count(self, obj):
        return obj.artifacts.count()


@admin.register(IncomingInvoiceArtifact)
class IncomingInvoiceArtifactAdmin(admin.ModelAdmin):
    list_display = ("display_name", "candidate", "kind", "content_type", "size", "is_invoice_like", "invoice_confidence")
    list_filter = ("kind", "is_invoice_like", "content_type")
    search_fields = ("original_filename", "sha256", "candidate__subject", "candidate__provider_message_id")
    autocomplete_fields = ("candidate",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    list_display = ("statement_number", "issuer", "customer", "from_date", "to_date", "total_balance")
    list_filter = ("issuer",)
    search_fields = ("statement_number", "customer__company__name")
    date_hierarchy = "from_date"
