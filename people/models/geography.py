from django.db import models


class Continent(models.Model):
    name=models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Country(models.Model):

    continent=models.ForeignKey(
        Continent,
        on_delete=models.PROTECT
    )

    code=models.CharField(
        max_length=5,
        unique=True
    )

    name=models.CharField(
        max_length=100
    )

    def __str__(self):
        return self.name


class Province(models.Model):

    country=models.ForeignKey(
        Country,
        on_delete=models.PROTECT
    )

    name=models.CharField(
        max_length=100
    )

    def __str__(self):
        return self.name


class Canton(models.Model):

    province=models.ForeignKey(
        Province,
        on_delete=models.PROTECT
    )

    name=models.CharField(
        max_length=100
    )

    def __str__(self):
        return self.name


class Parish(models.Model):

    canton=models.ForeignKey(
        Canton,
        on_delete=models.PROTECT
    )

    name=models.CharField(
        max_length=100
    )

    def __str__(self):
        return self.name