# 03 — الحالة القانونية والخط الزمني

## الحقول

الشكل القانوني، تاريخ التأسيس، الحالة الحالية، تاريخ الحل أو التصفية، الأسماء السابقة، تغييرات العنوان، والإيداعات المهمة.

## المصادر

- السجلات الرسمية الوطنية؛ [Companies House](https://www.gov.uk/government/organisations/companies-house/about/about-our-services) مثال غني بالحالة وتاريخ الإيداعات.
- [SEC EDGAR](https://www.sec.gov/search-filings) للأحداث والإفصاحات الخاصة بالشركات الخاضعة له.
- [GLEIF](https://www.gleif.org/en/lei-data/gleif-api) لحالة تسجيل LEI والكيان القانوني والتحديثات.
- [OpenCorporates](https://api.opencorporates.com/documentation/API-Reference) لتوحيد حقول من اختصاصات متعددة مع إرجاع المصدر.

## التفريق الضروري

- `entity_status`: حالة الشركة في السجل.
- `identifier_status`: مثل حالة LEI؛ قد تصبح lapsed دون أن تكون الشركة مغلقة.
- `operational_signal`: هل الموقع أو النشاط يبدو قائمًا؟ هذه إشارة وليست الحالة القانونية.

## نتيجة مقترحة

سجل أحداث غير قابل للمحو: `event_type`, `effective_date`, `recorded_date`, `value_before/after`, `source`. تعرض «الحالة الحالية» كاشتقاق من آخر دليل موثوق بدل الكتابة فوق التاريخ.

## حدود

حداثة السجلات تختلف، وبعض الحالات القانونية المحلية لا تترجم بدقة إلى `active/inactive`. احتفظ بالقيمة الأصلية ثم أضف قيمة معيارية منفصلة.

**يغطي أيضًا:** المخاطر، العمر، التمويل، والقدرة على التعاقد.

