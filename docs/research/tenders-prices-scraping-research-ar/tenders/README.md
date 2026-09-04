# تتبّع المناقصات وطرح المشروعات

> **RESEARCH.** `tenders` is a category the owner named and nothing collects yet.
> Its five apps are issues in milestone **#10**; the machinery they need —
> connector contract, manifest, source board, dataset jobs — largely exists, and
> each issue says which part.

## ما الذي يمكن للنظام فعله؟

يجمع الفرص الجديدة من مصادر متعددة، يوحّدها، يطابقها مع نشاط الشركة، ويراقب الموعد والمستندات والتعديلات والترسية والتنفيذ. كما يستطيع تتبع خطط ومشروعات مستقبلية قبل وصولها إلى مرحلة المناقصة إذا كان المصدر ينشر planning أو project pipeline.

## النقاط

| # | النقطة | الناتج الرئيسي |
|---:|---|---|
| 01 | [خريطة المصادر والبوابات](01-sources-portals.md) | قائمة موصلات وتغطية كل مصدر |
| 02 | [دورة المناقصة والإشعارات](02-lifecycle-notices.md) | planning → tender → award → contract → implementation |
| 03 | [البحث والتنبيهات والمطابقة](03-search-alerts-matching.md) | فرص مناسبة مع سبب ودرجة |
| 04 | [الجهات المشترية والموردون](04-buyers-suppliers-identity.md) | كيانات موحدة وسجل علاقاتها |
| 05 | [التصنيفات واللغات](05-classification-language.md) | CPV/UNSPSC/NAICS وكلمات مترجمة |
| 06 | [المواعيد والميزانية والأجزاء والأهلية](06-deadlines-value-lots-eligibility.md) | فرصة قابلة للتقييم والتقديم |
| 07 | [المستندات والمرفقات وOCR](07-documents-attachments-ocr.md) | نص قابل للبحث مع أصل الملف |
| 08 | [التعديلات والإلغاء وإزالة التكرار](08-changes-corrections-dedup.md) | timeline وتنبيه فروق حقيقي |
| 09 | [الترسية والعقود والتنفيذ والمنافسون](09-awards-contracts-performance.md) | فائز وقيمة وسجل سوق |
| 10 | [خطط المشروعات والتمويل والمنح](10-project-pipeline-funding.md) | فرص مبكرة مرتبطة بعقودها |
| 11 | [مؤشرات المخاطر والنزاهة](11-integrity-red-flags.md) | إشارات للمراجعة لا أحكام |
| 12 | [الأدوات المفتوحة والبنية والتكلفة](12-tools-architecture-cost.md) | Stack مقترح ومراحل تنفيذ |

## المصادر الأهم

| المصدر | النطاق | الوصول | ملاحظات |
|---|---|---|---|
| [OCP Data Registry](https://data.open-contracting.org/) | أكثر من 50 ناشر OCDS | تنزيلات مجمعة | أفضل نقطة لتعدد البلدان، والجودة تختلف |
| [TED Search API](https://docs.ted.europa.eu/api/latest/search.html) | مشتريات الاتحاد الأوروبي | بحث وتنزيل XML بلا مصادقة للمنشور | CPV وNUTS وإشعارات متعددة المراحل |
| [SAM.gov Opportunities API](https://open.gsa.gov/api/get-opportunities-public-api/) | فرص التعاقد الفيدرالية الأمريكية | API بمفتاح وحصص | API يعرض أحدث نسخة نشطة؛ التاريخ عبر Data Services |
| [UK Open Contracting](https://www.gov.uk/government/publications/open-contracting) | Find a Tender وContracts Finder | OCDS JSON/XML | يوفر release/record APIs |
| [Etimad API Portal](https://portal.etimad.sa/) | السعودية | منتجات API وشروط اشتراك | تحقق من المنتج والصلاحية المتاحين؛ لا تفترض أن كل المناقصات endpoint عام |
| [UAE Digital Procurement Platform](https://mof.gov.ae/ar/public-finance/government-procurement/digital-procurement-platform/) | مشتريات اتحادية إماراتية | بوابة وفرص عامة | التقديم والتتبع الكامل يتطلب تسجيل مورد |
| [UNGM](https://www.ungm.org/Public/Notice) | وكالات الأمم المتحدة | بحث عام؛ API موثق ومصادق | [API البحث](https://developer.ungm.org/Article/SearchNotices) موجه لإشعارات الوكالة المصرح بها، فلا يُفترض أنه bulk عام |
| [World Bank Projects & Operations](https://datacatalog.worldbank.org/search/dataset/0037800/world-bank-projects-operations) | مشروعات وتمويل وعقود البنك الدولي | datasets وProjects API | project ID يربط المشروعات والوثائق والمنح وبعض awards |
| [IATI APIs](https://developer.iatistandard.org/) | أنشطة وتمويل التنمية والمساعدات | APIs وDatastore | مشاريع/أنشطة وليست كلها مناقصات |
| [OC4IDS](https://standard.open-contracting.org/infrastructure/latest/en/reference/) | مشروعات البنية التحتية | معيار وبيانات ناشرين | يربط project lifecycle بعمليات التعاقد |

## أدوات تغطي أكثر من نقطة

| الأداة | الدور |
|---|---|
| [Kingfisher Collect](https://github.com/open-contracting/kingfisher-collect) | تنزيل مصادر OCDS دوريًا وتوحيد packages؛ BSD-3-Clause |
| [OCDS Kit](https://github.com/open-contracting/ocdskit) | merge/split/upgrade/compile لحزم OCDS؛ BSD-3-Clause |
| [Lib CoVE OCDS](https://github.com/open-contracting/lib-cove-ocds) | فحص بنية وجودة ملفات OCDS |
| [Flatten Tool](https://github.com/OpenDataServices/flatten-tool) | تحويل JSON المنظم إلى CSV/XLSX والعكس |
| [OCDS Cardinal](https://github.com/open-contracting/cardinal-rs) | حساب مؤشرات وred flags من OCDS؛ MIT |
| [Open Contracting Portal](https://github.com/devgateway/ocportal) | استيراد وعرض وتحليل OCDS؛ MIT، لكنه أقرب لمنصة تحليل مرجعية من محرك تنبيهات جاهز |
| Scrapy/Playwright وطبقة scraping في القسم الثالث | البوابات التي لا توفر API/Feed مسموحًا |

## السيناريو العام

```text
ملف الشركة: منتجات + خدمات + أكواد + دول + حد قيمة
                         ↓
API/OCDS/Feeds ← Source Connectors → HTML/PDF عند الحاجة
                         ↓
توحيد إلى Tender + Notice + Lot + Document + Party
                         ↓
إزالة التكرار وربط كل إصدار بالعملية نفسها
                         ↓
فلترة إلزامية ثم scoring نصي/دلالي
                         ↓
فرصة مناسبة + سبب المطابقة + الموعد + المستندات
                         ↓
مراقبة التعديل/التمديد/الإلغاء/الترسية والتنفيذ
```

## الخلاصة

أقوى أساس مفتوح هو OCDS مع موصلات رسمية لـTED وSAM وبريطانيا، ثم موصلات محلية لاعتماد وبوابات الإمارات وغيرها. لا يوجد مشروع مفتوح جاهز يغطي كل البلدان والتنبيهات والمطابقة والجودة دفعة واحدة؛ لكن توجد مكونات ممتازة تمنع بناء طبقة الجمع والتوحيد من الصفر.

