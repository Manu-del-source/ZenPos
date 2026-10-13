"""The eTIMS adapter interface (ADR-0019).

The invoice domain records *that* an invoice exists; the adapter knows *how*
it reaches the tax authority. Today the only adapter records locally — the
invoice row is the document — and transmits nothing, so this deployment
makes no KRA calls and makes no compliance claims. The transmission
contract is pinned here so a verified URS adapter slots in without touching
the sales or invoice layers.
"""

from abc import ABC, abstractmethod


class EtimsAdapter(ABC):
    #: Stored on audit rows so the history shows which adapter acted.
    adapter_name: str = ""

    @abstractmethod
    def issue(self, *, invoice) -> None:
        """Issue one invoice.

        A transmitting adapter sends the document and writes the
        KRA-assigned UIN onto the row before returning. It must not change
        the invoice's status — the row's lifecycle is owned by the service
        layer, and an adapter that marks things done it did not do is how
        compliance claims go wrong.
        """

    @abstractmethod
    def cancel(self, *, invoice) -> None:
        """Cancel an issued invoice whose sale was voided.

        A transmitting adapter notifies the authority. The row's CANCELLED
        state is set by the caller either way, so a transmission failure
        surfaces as an error rather than a silent document — the service
        layer rolls the row back with the transaction.
        """


class LocalRecordingAdapter(EtimsAdapter):
    """The recording-only adapter: the invoice row is the document.

    It transmits nothing, assigns no UIN, and makes no claim that any tax
    authority has seen the invoice. It exists so the whole invoice
    lifecycle — issue, cancel, reconcile, void — is real and tested before
    a verified transmission adapter is added.
    """

    adapter_name = "local"

    def issue(self, *, invoice) -> None:
        return None

    def cancel(self, *, invoice) -> None:
        return None
