# 01 — خريطة المصادر والبوابات

## أنواع المصادر

1. API أو bulk رسمي: الأفضل للثبات والحقول المنظمة.
2. OCDS: يسمح بتوحيد ناشرين متعددين.
3. RSS/Atom/CSV/XML: جيد للتحديث الدوري.
4. بوابة بحث HTML عامة: scraper محدود مع احترام الشروط.
5. منطقة مورد بعد login: لا تُؤتمت إلا إذا سمحت الجهة والحساب بذلك صراحة.

## البداية المقترحة

- متعدد الدول: [OCP Data Registry](https://data.open-contracting.org/) و[Kingfisher Collect](https://github.com/open-contracting/kingfisher-collect).
- أوروبا: [TED Search API](https://docs.ted.europa.eu/api/latest/search.html).
- الولايات المتحدة: [SAM.gov Public Opportunities API](https://open.gsa.gov/api/get-opportunities-public-api/).
- بريطانيا: [Find a Tender/Contracts Finder OCDS](https://www.gov.uk/government/publications/open-contracting).
- السعودية: [بوابة اعتماد API](https://portal.etimad.sa/) والصفحات العامة المتاحة وفق الشروط.
- الإمارات: [منصة المشتريات الرقمية](https://mof.gov.ae/ar/public-finance/government-procurement/digital-procurement-platform/) وبوابات الإمارة.
- الأمم المتحدة: [UNGM public notices](https://www.ungm.org/Public/Notice)، مع فهم أن API الموثق يتطلب صلاحيات ولا يمثل bulk عامًا تلقائيًا.

## سجل الموصل

لكل مصدر: البلد، التغطية، طريقة الوصول، الترخيص، الحصة، timezone، التصنيفات، المراحل، توفر الملفات، آخر نجاح وإصدار parser.

## قاعدة

لا تُسمِّ المصدر «مغطى» لمجرد فتح الصفحة؛ يلزم اختبار pagination والتاريخ والتعديلات والملفات وما إذا كانت النتائج كاملة.

