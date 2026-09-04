# 18 — تغيير SIM

## السؤال

هل رُبط رقم الهاتف بشريحة SIM جديدة مؤخرًا؟

## ما الذي تثبته؟

تغيير SIM إشارة أمنية مهمة قبل تسجيل الدخول أو استعادة حساب أو عملية حساسة. لا يعني وحده الاحتيال؛ يمكن أن يكون استبدالًا طبيعيًا لشريحة تالفة، eSIM، ترقية، أو تغيير خدمة.

## الأدوات والخدمات

- [CAMARA SIM Swap](https://github.com/camaraproject/SimSwap/blob/main/code/API_definitions/sim-swap.yaml): مواصفة Apache-2.0 تسأل عن تاريخ آخر تغيير أو وقوع تغيير خلال فترة محددة. التنفيذ الفعلي يحتاج مزود شبكة وتفويضًا.
- [Twilio SIM Swap](https://www.twilio.com/docs/lookup/v2-api): مذكور كتغطية محدودة في أوروبا وأمريكا اللاتينية وأمريكا الشمالية، مع موافقات Carrier.
- [Vonage Identity Insights](https://developer.vonage.com/de/api/number-insight?source=number-insight): يجمع SIM Swap وSubscriber Match وCarrier data.
- [Telesign Phone ID](https://www.telesign.com/products/phone-id): يقدم إشارات SIM swap وPorting وCall forwarding ضمن عروض المخاطر بحسب التغطية.

الأدوات نفسها تغطي Ownership وPorting وCurrent Carrier؛ لذلك توضع SIM Swap داخل Risk App وتُستدعى عند حدث حساس، لا لكل رقم في الـCrawl.

## النتيجة المقترحة

```text
sim_swap_status: recent | not_recent | no_data | unknown
last_sim_swap_at
lookback_window_hours
provider
checked_at
```

## قواعد القرار

- `recent` يرفع المخاطرة ويطلب تحققًا إضافيًا؛ لا يحكم بالاحتيال.
- `no_data` لا يساوي عدم وجود تغيير.
- نحتفظ بنافذة الاستعلام لأن تعريف «حديث» يعتمد على العملية.
- البيانات شديدة الحساسية ولا تُجمع بلا سبب واضح.
- لا قيمة كبيرة لهذه الإشارة في مجرد تنظيف قائمة أرقام؛ قيمتها في حماية الحسابات والمعاملات.

## التوصية

نبقي Adapter لـSIM Swap ضمن التصميم، لكنه غير مفعل في النسخة الأولى. يُستخدم فقط إذا أضيف تسجيل دخول أو إثبات ملكية أو عمليات حساسة.

## المصادر

- [CAMARA SIM Swap specification](https://github.com/camaraproject/SimSwap/blob/main/code/API_definitions/sim-swap.yaml)
- [Twilio Lookup v2](https://www.twilio.com/docs/lookup/v2-api)
- [Vonage Number Insight](https://developer.vonage.com/de/api/number-insight?source=number-insight)

