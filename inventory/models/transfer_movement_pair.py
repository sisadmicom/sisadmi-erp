from django.db import models
from django.db.models import F, Q

from .stock_movement import StockMovement
from .transfer import Transfer


class TransferMovementPair(models.Model):
    transfer = models.ForeignKey(Transfer, on_delete=models.PROTECT, related_name="movement_pairs")
    out_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="transfer_out_pair")
    in_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="transfer_in_pair")

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(out_movement=F("in_movement")), name="transfer_pair_distinct_movements")]
