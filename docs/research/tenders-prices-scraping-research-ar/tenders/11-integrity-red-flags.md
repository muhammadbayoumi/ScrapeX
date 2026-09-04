# 11 — مؤشرات المخاطر والنزاهة

## ما الذي يمكن حسابه؟

منافس واحد، طريقة غير تنافسية، مدة تقديم قصيرة، نشر متأخر، تركّز فوز مورد، تعديلات كبيرة، تجزئة محتملة، تضارب توقيت أو سعر شاذ.

## أدوات ومنهجيات

- [OCP Red Flags Guide](https://www.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/) يربط عشرات المؤشرات بـOCDS.
- [OCDS Cardinal](https://github.com/open-contracting/cardinal-rs) يحسب مؤشرات وred flags من البيانات المنظمة؛ MIT.
- [OECD bid-rigging checklist](https://www.oecd.org/en/publications/oecd-guidelines-for-fighting-bid-rigging-in-public-procurement-2025-update_cbe05a56-en/full-report/component-5.html) مرجع للسلوكيات والأنماط.
- حزمة إثراء الشركات للملكية والعقوبات وسجل المورد، مع قواعد قانونية منفصلة.

## قاعدة حاسمة

Red flag = سبب للمراجعة، وليس إثبات فساد أو تواطؤ. اعرض formula والحقول المستخدمة والبيانات المفقودة ومجموعة المقارنة.

## النتيجة

`indicator_id`, القيمة/العتبة، الفترة، evidence، coverage، severity، وحالة المراجعة. لا تجمعها في score غامض؛ يمكن summary مع إبقاء التفاصيل.

## حدود

مناقصة متخصصة قد يكون لها مورد واحد طبيعيًا. السعر الشاذ يحتاج مواصفة وكمية ومكان وزمن متقاربًا.

