from django.contrib import admin

from invoices.models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('paid_date', 'amount', 'issuer', 'customer', 'project')
    list_filter = ('issuer', 'customer')
    search_fields = ('description',)
