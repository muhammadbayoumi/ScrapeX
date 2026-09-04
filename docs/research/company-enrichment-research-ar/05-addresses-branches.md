# 05 — العناوين والفروع والمواقع

## الأنواع التي يجب فصلها

- عنوان مسجل قانونيًا.
- مقر رئيسي أو عنوان تشغيل.
- عنوان مراسلات.
- فرع/متجر/مصنع/مكتب.
- عنوان سابق.

## المصادر

- السجل الوطني و[OpenCorporates](https://api.opencorporates.com/documentation/API-Reference).
- [GLEIF](https://www.gleif.org/en/lei-data/gleif-api) للعنوان القانوني وعنوان المقر في سجلات LEI.
- الإيداعات والتقارير عبر [SEC EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
- صفحات Contact/Locations وبيانات [Schema.org Organization](https://schema.org/Organization) بالموقع.
- ناشرو [OCDS](https://data.open-contracting.org/) و[USAspending](https://api.usaspending.gov/) قد يكشفون عناوين الموردين.

## المعالجة

حافظ على النص الأصلي، ثم طبّع البلد والمدينة والرمز البريدي والمكونات. يمكن إضافة إحداثيات من مصدر خرائط مفتوح، لكن لا تستبدل العنوان القانوني بنتيجة geocoder.

## نتيجة مقترحة

لكل عنوان: `address_type`, النص الأصلي، المكونات، الإحداثيات إن وجدت، `valid_from/to`, المصدر والثقة.

## حدود

العنوان المسجل قد يكون مكتب محاماة أو وكيلًا ولا يدل على نشاط فعلي. مشاركة عدة شركات عنوانًا واحدًا ليست وحدها علامة احتيال.

**يغطي أيضًا:** حل الهوية، الفروع، الاختصاص، والعقود.

