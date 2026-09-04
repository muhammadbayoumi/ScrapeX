# 12 — الأدوات المفتوحة والبنية والتكلفة

## Stack مرشح، وليس قرار تنفيذ

| الطبقة | مشروعات مناسبة |
|---|---|
| OCDS collection | [Kingfisher Collect](https://github.com/open-contracting/kingfisher-collect) |
| OCDS transforms | [OCDS Kit](https://github.com/open-contracting/ocdskit)، [Flatten Tool](https://github.com/OpenDataServices/flatten-tool) |
| validation | [Lib CoVE OCDS](https://github.com/open-contracting/lib-cove-ocds) |
| indicators | [OCDS Cardinal](https://github.com/open-contracting/cardinal-rs) |
| تحليل/عرض مرجعي | [Open Contracting Portal](https://github.com/devgateway/ocportal) |
| HTML/JS/PDF | طبقة scraping المشتركة في الحزمة |
| entity resolution | حزمة إثراء الشركات السابقة |

## البنية

كل source adapter ينتج schema داخليًا قريبًا من OCDS حتى إن كان المصدر HTML. job scheduler يستدعي adapters، raw store يحفظ الدليل، normalizer ينتج releases، matcher يولد فرص المستخدم، watcher يحسب الفرق، ثم notifications.

## التكلفة

- الأدوات المذكورة مفتوحة؛ تكلفة الترخيص غالبًا صفر، مع مراجعة license لكل dependency.
- APIs الحكومية قد تحتاج مفتاحًا وحصة بلا رسوم.
- الملفات والمتصفحات والترجمة/LLM تزيد compute والتخزين.
- أكبر تكلفة هي بناء وصيانة adapter لكل بوابة غير منظمة.

## مراحل التنفيذ

1. TED + مصدر OCDS واحد + ملف شركة يدوي.
2. SAM/UK ومصادر البلد المستهدف.
3. مستندات وOCR والتعديلات.
4. awards/project pipeline/red flags.

لا يُختار stack نهائي قبل فحص التقنية الموجودة فعليًا في الأداة والـcrawler.

