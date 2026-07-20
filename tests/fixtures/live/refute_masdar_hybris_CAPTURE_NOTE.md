# MASDAR / hybris-occ live capture (refuter pass)

Captured 2026-07-20 by the independent refuter.

URLs (verbatim, HTTP 200, application/json;charset=UTF-8):
- https://api.masdaronline.com/rest/v2/masdar/products/search?fields=FULL&pageSize=100&currentPage=0&query=%3Arelevance
  -> refute_masdar_hybris_page0_2026-07-20.json
- https://api.masdaronline.com/rest/v2/masdar/products/search?fields=FULL&pageSize=100&currentPage=1&query=%3Arelevance
  -> refute_masdar_hybris_page1_2026-07-20.json

Byte-faithful, untrimmed. User-Agent: ScrapeX-audit/1.0.
pagination: {"currentPage":0,"pageSize":100,"sort":"relevance","totalPages":14,"totalResults":1354}

Key finding reproduced: price.value == priceWithTax.value for 100/100 priced
products on BOTH pages; price.value == priceWithoutTax.value for 0/100.
e.g. code 1000061922: price 206.99999999999997 / priceWithTax 206.99999999999997
/ priceWithoutTax 180.0 (180 x 1.15 = 207, SA VAT 15%).
=> sources.yaml vat_mode: excl for MASDAR is BACKWARDS.
