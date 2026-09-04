# 10 — خطط المشروعات والتمويل والمنح

## الفرق

المناقصة فرصة طلب عروض حالية؛ project pipeline قد يكون فكرة أو تمويلًا أو دراسة جدوى قبل الطرح. تتبع الاثنين يمنح إنذارًا مبكرًا لكن لا يعني أن المشروع سيطرح.

## المصادر المفتوحة

- [OC4IDS](https://standard.open-contracting.org/infrastructure/latest/en/reference/) لبيانات مشروع البنية التحتية من identification إلى التشغيل وربطه بعقود OCDS.
- [World Bank Projects & Operations](https://datacatalog.worldbank.org/search/dataset/0037800/world-bank-projects-operations): project ID، بلد، قطاع، تمويل، وثائق وبعض awards.
- [IATI APIs/Datastore](https://developer.iatistandard.org/) لأنشطة التنمية والميزانيات والمعاملات.
- [CORDIS](https://cordis.europa.eu/about/services) لمشروعات وتمويل البحث الأوروبي.
- خطط الشراء السنوية والميزانيات المنشورة محليًا.

## النموذج

`project` مستقل عن `contracting_process` مع علاقات `funded_by`, `procures_via`, `part_of_program`. خزّن stage، التمويل، الموقع، القطاع، التواريخ والمستندات.

## حدود

لا تحوّل project announcement إلى tender alert. استخدم نوع تنبيه «فرصة مستقبلية»، وثقة منفصلة لاحتمال الطرح وتاريخه. قد تتغير الميزانية والنطاق أو يلغى المشروع.

