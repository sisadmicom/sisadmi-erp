from django.contrib import admin

from core.models.company import Company
from core.models.branch import Branch

admin.site.register(Company)
admin.site.register(Branch)