from django.contrib import admin
from .models import Experiment


@admin.register(Experiment)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'last_update_date', 'stopped', 'cohort_filled', 'calculation_finished')
    list_filter = ('stopped', 'cohort_filled', 'calculation_finished')
    search_fields = ('name', 'id')
    date_hierarchy = 'last_update_date'
    readonly_fields = ('last_update_date',)
