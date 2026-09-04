# تتبّع أسعار المنتجات بالمصادر والأدوات المفتوحة

> **RESEARCH.** `prices` is the category ScrapeX was built on, so most of what
> follows is already shipped: `price_observation`, `price_period`,
> `change_event`, nine connectors and one `normalize` module. The three apps are
> issues in milestone **#10** and each leads with what exists.

## الإجابة

يمكن بناء نظام شخصي يتتبع سعر منتج من متجر واحد أو يقارن عدة بائعين ويحتفظ بتاريخ وينبه عند الهبوط أو عودة المخزون. توجد أدوات جاهزة ممتازة، لكن «استخراج رقم السعر» أسهل جزء؛ الأصعب هو التأكد أن المقارنة لنفس المنتج والنسخة والكمية والسوق، وأن السعر النهائي يشمل الشحن والضريبة والشروط ذات الصلة.

## النقاط

| # | النقطة | أهم ناتج |
|---:|---|---|
| 01 | [هوية المنتج والمطابقة](01-product-identity-matching.md) | product موحد وروابط offers |
| 02 | [السعر الحالي والعرض](02-current-price-offer.md) | مبلغ وعملة ونوع سعر ودليل |
| 03 | [النسخ والعبوات وسعر الوحدة](03-variants-packs-unit-price.md) | مقارنة عادلة بين variants |
| 04 | [البائعون والمتاجر والأسواق](04-sellers-marketplaces.md) | seller/merchant/marketplace منفصلون |
| 05 | [المخزون والتوفر والتوصيل](05-stock-availability-delivery.md) | حالة قابلة للتنبيه |
| 06 | [العروض والكوبونات والعضوية](06-promotions-coupons-membership.md) | سعر مشروط ومدة العرض |
| 07 | [الشحن والضريبة والسعر النهائي](07-shipping-tax-landed-price.md) | landed price حسب الموقع |
| 08 | [الموقع والتخصيص والأسعار الديناميكية](08-location-personalization-dynamic.md) | سياق الرصد الكامل |
| 09 | [التاريخ والتغييرات والتنبيهات](09-history-changes-alerts.md) | snapshots وprice events |
| 10 | [قواعد البيانات وواجهات المنتجات المفتوحة](10-open-product-price-data.md) | مصادر جاهزة وحدود تغطيتها |
| 11 | [مشروعات وأدوات التتبع المفتوحة](11-open-source-trackers.md) | خيارات جاهزة للمراقبة |
| 12 | [التطبيع والجودة والالتزام والتكلفة](12-normalization-quality-cost.md) | نتيجة موثوقة وقابلة للمراجعة |

## الأدوات والمصادر متعددة التغطية

| المشروع/المصدر | ماذا يغطي؟ | الملاحظات |
|---|---|---|
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io) | صفحات ديناميكية، price/restock، filters، history، notifications وAPI | self-hosted؛ Apache-2.0 بحسب [API docs](https://changedetection.io/docs/api_v1/)؛ أفضل MVP عام |
| [urlwatch](https://github.com/thp/urlwatch) | مراقبة أجزاء HTML/JSON والنص وإرسال diff وتنبيهات | خفيف وملائم للـCLI؛ تحتاج تحديد السعر/الفلتر بنفسك |
| [Huginn](https://github.com/huginn/huginn) | agents للجلب والاستخراج والجدولة والتحويل والتنبيه | MIT؛ مرن لكنه أثقل في الإعداد من price watcher مباشر |
| [Open Prices](https://prices.openfoodfacts.org/) | أسعار غذاء مع منتج ومكان وتاريخ ودليل | بيانات crowdsourced وليست تغطية كل متجر؛ ODbL ومتطلبات attribution/share-alike |
| [Open Food Facts API](https://openfoodfacts.github.io/openfoodfacts-server/api/) | هوية منتجات غذائية بالباركود وصور وخصائص | جيد لـGTIN الغذاء؛ الجودة والتغطية مجتمعية |
| [Schema.org Product/Offer](https://schema.org/Product) + [extruct](https://github.com/scrapinghub/extruct) | GTIN/SKU/brand/variant/price/currency/availability عندما ينشرها المتجر | أسرع من selectors، لكنه ادعاء الصفحة وقد يكون قديمًا |
| [price-parser](https://github.com/scrapinghub/price-parser) | تحويل نص السعر إلى مبلغ وعملة | BSD-3-Clause؛ لا يحدد هل السعر بيع أم قديم ولا يحسب الشحن |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | مطابقة أسماء وموديلات تقريبية | أداة مساعدة؛ GTIN/MPN أقوى |
| [Frankfurter](https://frankfurter.dev/) / [ECB Data API](https://data.ecb.europa.eu/help/getting-data-web-services-sdmx-0) | تحويل العملة تاريخيًا | أسعار مرجعية يومية وليست سعر بطاقة/معاملة |
| Scrapy/Crawlee/Playwright | جمع مخصص لمتاجر متعددة | أقوى تحكم، وأعلى تكلفة صيانة |

## متى نستخدم ماذا؟

- رابط أو عشرات الروابط وتنبيه شخصي: `changedetection.io`.
- مراقبة نص/JSON بخادم صغير: `urlwatch`.
- workflow يجمع ويحوّل ويرسل إلى عدة قنوات: `Huginn`.
- غذاء بالباركود وأسعار مجتمعية: Open Food Facts + Open Prices.
- آلاف المنتجات وعدة متاجر: محرك scraping + Product Resolver + قاعدة history.

## نموذج البيانات

```json
{
  "product_id": "internal-product",
  "offer_id": "seller|sku|market|condition",
  "seller": "Example Store",
  "market": "SA",
  "variant": {"color": "black", "size": "256GB", "pack": 1},
  "price": {"amount": "3499.00", "currency": "SAR", "type": "sale"},
  "shipping": {"amount": "0.00", "postal_code": "..."},
  "availability": "in_stock",
  "observed_at": "2026-09-04T00:00:00Z",
  "source_url": "https://...",
  "extraction": "json_ld",
  "confidence": 0.96
}
```

## ما لا يوجد مفتوحًا بالكامل

- لا توجد قاعدة عالمية مفتوحة للأسعار الحية لكل المنتجات والمتاجر.
- Keepa وCamelCamelCamel وخدمات مقارنة الأسعار مفيدة في نطاقها لكنها ليست قواعد مفتوحة أو مشروعات self-hosted عامة.
- GTIN يساعد على الهوية ولا يحتوي السعر؛ السعر مرتبط ببائع ومكان وزمن وشروط.
- كثير من الأسواق تمنع أو تقيد automated access؛ API/affiliate/product feed الرسمي يتقدم على scraping.

## السيناريو

```text
URL / barcode / اسم منتج
       ↓
Product Resolver: GTIN > MPN+Brand > SKU per seller > fuzzy candidate
       ↓
Offer Extractor: JSON-LD/API/feed ثم HTML ثم browser عند الحاجة
       ↓
Validation: amount + currency + variant + seller + availability + context
       ↓
Append-only snapshot
       ↓
Price event: drop/rise/promotion/restock/error
       ↓
Alert حسب قاعدة المستخدم مع رابط ودليل
```

## الخلاصة

أفضل بداية شخصية هي changedetection.io كـApp سريع، ثم `Price Collector` مخصص يستخدم `extruct + price-parser` ويشارك طبقة Scrapy/Playwright مع باقي المنظومة. Open Prices إضافة ممتازة للغذاء وليست بديلًا عن مراقبة المتاجر المطلوبة.

