"""One module per site whose pages ScrapeX knows how to enumerate.

A `PageSource` (see `scrapex/pagesource.py`) is NOT a connector. Connectors live
in `scrapex/connectors/` and return priced offers; these return only pages, and
what a page means is decided later, against a stored snapshot. Keeping the two
in separate packages is the cheapest way to stop somebody writing a generic
source against `SiteConnector` — which would compile, pass, and put nothing in
the generic tables.
"""
