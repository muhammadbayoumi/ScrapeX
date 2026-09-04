# 01 — تنسيق الرقم وتوحيده

## السؤال

هل يمكن تحويل النص المكتشف إلى رقم هاتف موحد يمكن مقارنته وتخزينه وفحصه؟

## ما الذي تثبته هذه النقطة؟

تثبت أن النص قابل للتحليل كرقم هاتف في سياق دولة معينة، ويمكن تحويله إلى صيغة دولية مثل E.164. لا تثبت أن الرقم مخصص فعليًا، أو أن الخط حي، أو أن شخصًا يملكه الآن.

## الأدوات المفتوحة المصدر

- [Google libphonenumber](https://github.com/google/libphonenumber): المرجع الأساسي للتحليل والتنسيق الدولي.
- [libphonenumber-js](https://github.com/catamphetamine/libphonenumber-js): مناسب لبيئات JavaScript.
- [python-phonenumbers](https://github.com/daviddrysdale/python-phonenumbers): منفذ Python بترخيص Apache-2.0.

هذه الأدوات تغطي أيضًا النقاط 2 و3 و4، ويمكن لـlibphonenumber تقديم اسم الشركة الأصلية ضمن النقطة 5.

## المدخلات المهمة

- النص الخام كما ظهر في الصفحة.
- الدولة الافتراضية المستنتجة من الصفحة أو المصدر.
- وجود `+` أو كود اتصال دولي.
- الامتداد الداخلي مثل `ext 123`.
- سياق الصفحة؛ لأن الرقم المحلي قد يكون غامضًا دون دولة.

## النتيجة المقترحة

```text
parse_status: parsed | ambiguous | invalid
raw_number
e164
national_format
international_format
extension
assumed_country
assumption_source
```

## قواعد القرار

- لا نفقد النص الخام بعد التطبيع.
- لا نخمن دولة بلا تسجيل سبب التخمين.
- أرقام الدول المشتركة في نفس كود الاتصال قد تظل غامضة.
- تجرى إزالة التكرارات باستخدام E.164، مع الاحتفاظ بكل مصادر الظهور.
- الأرقام القصيرة وأرقام الخدمات والطوارئ تحتاج مسارًا منفصلًا ولا تعامل كأرقام مشتركين عادية.

## التوصية

هذه أول مرحلة إلزامية ومجانية. تُنفذ محليًا على كل الأرقام قبل أي API خارجي، وتُستخدم نتيجتها كمفتاح موحد لباقي التطبيقات.

## المصادر

- [Google libphonenumber](https://github.com/google/libphonenumber)
- [libphonenumber-js validation and metadata](https://github.com/catamphetamine/libphonenumber-js/blob/master/README.md)

