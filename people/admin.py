from django.contrib import admin
from people.models.person import Person
from people.models.geography import Continent,Country,Province,Canton,Parish

admin.site.register(Person)
admin.site.register(Country)
admin.site.register(Continent)
admin.site.register(Province)
admin.site.register(Canton)
admin.site.register(Parish)