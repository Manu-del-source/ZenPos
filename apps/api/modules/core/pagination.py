"""The project's default pagination.

DRF's ``PageNumberPagination`` ignores ``?page_size=`` unless a subclass opts
in, so the POS asking for 100 products silently received the server default of
50 — a supermarket shelf that stops at the fiftieth item is a bug the cashier
cannot see. Clients may now ask for a larger page, up to a ceiling that keeps
one request from turning into a table scan.
"""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
