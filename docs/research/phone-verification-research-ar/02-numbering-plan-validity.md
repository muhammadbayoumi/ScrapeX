# 02 — صلاحية خطة الترقيم

## السؤال

هل عدد الخانات والمقدمة والنمط يتوافق مع خطة الترقيم المعروفة للدولة؟

## ما الذي تثبته؟

تثبت أن الرقم `possible` أو `valid according to metadata`. هذا فحص بنيوي فقط، وليس اتصالًا بشبكة الهاتف. الرقم قد يطابق الخطة لكنه غير مخصص، مفصول، أو أُعيد تخصيصه.

## الأدوات

- [Google libphonenumber](https://github.com/google/libphonenumber) يوفر `isPossibleNumber` و`isValidNumber`.
- [libphonenumber-js](https://github.com/catamphetamine/libphonenumber-js) يوفر `isPossible()` و`isValid()`؛ وللدقة الأعلى ينبغي استخدام `max` metadata بدل الحزمة المصغرة.
- [Twilio Basic Lookup](https://www.twilio.com/docs/lookup/quickstart) يقدم فحصًا أساسيًا وتنسيقًا عبر API.
- [HLR Lookup Validate](https://www.hlrlookup.com/docs/hlrlookup-docs.html) يوفر فحصًا Offline دون لمس الشبكة.

الأدوات نفسها تغطي النقطة 1، وقد تستخرج الدولة والنوع في النقطتين 3 و4.

## النتيجة المقترحة

```text
possible: true | false | unknown
metadata_valid: true | false | unknown
validation_reason: too_short | too_long | invalid_prefix | valid_pattern | ambiguous
metadata_version
```

## قواعد القرار

- `possible` أضعف من `metadata_valid`؛ الأول قد يفحص الطول فقط.
- تحديث metadata مهم لأن خطط الترقيم تتغير وتضاف نطاقات جديدة.
- `metadata_valid=true` لا يعني `line_status=live`.
- عند غياب الدولة الافتراضية، تُعاد النتيجة `ambiguous` بدل اختيار دولة عشوائيًا.

## التوصية

نجعل هذه المرحلة مجانية ومحلية. الأرقام الفاشلة بنيويًا لا تنتقل إلى فحوص مدفوعة، أما الأرقام الناجحة فتنتقل إلى الطبقات التالية دون منحها وصف «حي».

## المصادر

- [Google libphonenumber](https://github.com/google/libphonenumber)
- [libphonenumber-js README](https://github.com/catamphetamine/libphonenumber-js/blob/master/README.md)
- [Twilio Lookup quickstart](https://www.twilio.com/docs/lookup/quickstart)

