"""Read-only historical evidence; never classification or backfill authority."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CustomerCompanyEvidence:
    customer_id: int
    assigned_company_id: int | None
    document_company_ids: frozenset[int]

    @property
    def candidate_company_id(self):
        """One observed company is only a candidate for explicit classification."""
        if len(self.document_company_ids) == 1:
            return next(iter(self.document_company_ids))
        return None

    @property
    def is_ambiguous(self):
        return len(self.document_company_ids) > 1


def inspect_customer_company_evidence(customer):
    return CustomerCompanyEvidence(
        customer_id=customer.pk,
        assigned_company_id=customer.company_id,
        document_company_ids=frozenset(customer.sales.order_by().values_list("company_id", flat=True).distinct()),
    )
