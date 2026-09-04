# 17 — إعادة تخصيص الرقم

## السؤال

هل أوقفت شركة الاتصالات الرقم ثم منحته لاحقًا لشخص جديد؟

## لماذا هذه النقطة مهمة؟

رقم كان صحيحًا ومرتبطًا باسم أو موافقة قديمة يمكن أن ينتقل إلى مالك جديد. هذا يجعل Caller Name وسجل التواصل والموافقة القديمة غير موثوقين حتى لو ظل الرقم حيًا.

## الأدوات والخدمات

- [FCC Reassigned Numbers Database](https://www.reassigned.us/sites/default/files/resources/userguides/QueryUserGuide_2.pdf): قاعدة رسمية للولايات المتحدة، وتجيب عادة بناءً على الرقم وتاريخ آخر موافقة أو تواصل.
- [Twilio Reassigned Number](https://www.twilio.com/docs/lookup/v2-api): حزمة مذكورة للولايات المتحدة فقط وتتطلب وصولًا مناسبًا.
- [Telesign Number Deactivation](https://www.telesign.com/services): يوفر تاريخ التعطيل وتنبيهات على فصل الرقم أو نقله حسب المنتج.
- [CAMARA Number Recycling](https://camaraproject.org/number-recycling/): مواصفة/مشروع مفتوح لفحص تغير مشترك الرقم، لكن التوفر يعتمد على المشغل.

لا توجد قاعدة عالمية مفتوحة كاملة؛ إعادة التخصيص تعتمد على سجلات المشغلين والقواعد المحلية.

## النتيجة المقترحة

```text
reassigned_status: yes | no | no_data | unknown
query_reference_date
disconnect_or_change_date
coverage_country
source
checked_at
```

## قواعد القرار

- `no_data` لا يساوي `no`.
- عند `yes` لا نحذف الرقم، بل نفصل علاقته بالاسم والموافقة القديمة.
- يجب أن يكون الاستعلام مرتبطًا بتاريخ؛ السؤال ليس «هل أعيد تخصيصه يومًا؟» فقط، بل «هل تغير بعد آخر علاقة موثوقة؟».
- ظهور اسم مختلف حديثًا مع Reassignment يعزز احتمال تغير المالك.

## التوصية

نفعل هذه النقطة للدول أو الحالات التي تتوفر لها بيانات موثوقة، وخاصة قبل إعادة استخدام موافقة قديمة أو التواصل بعد فترة طويلة. خارج التغطية تبقى النتيجة `unknown`.

## المصادر

- [FCC RND Query User Guide](https://www.reassigned.us/sites/default/files/resources/userguides/QueryUserGuide_2.pdf)
- [Twilio Lookup Reassigned Number](https://www.twilio.com/docs/lookup/v2-api)
- [Telesign services](https://www.telesign.com/services)

