# 07 — هل الخط حي وقابل للوصول؟

## السؤال

هل الرقم موجود حاليًا لدى شبكة اتصالات، وهل يبدو متصلًا أو قابلًا للوصول؟

## ما الذي تثبته؟

تعطي HLR أو Line Status مؤشرًا قويًا على حالة الخط، لكنها لا تضمن نجاح رسالة أو مكالمة بعينها. قد يكون الهاتف مغلقًا مؤقتًا، خارج التغطية، في Roaming، أو تمنع الشبكة الاستعلام.

## الأدوات والخدمات

- [HLR Lookup](https://www.hlrlookup.com/docs/hlrlookup-docs.html): حالات مثل `LIVE` و`DEAD` و`ABSENT_SUBSCRIBER` مع الشبكة الحالية.
- [Twilio Lookup Line Status](https://www.twilio.com/docs/lookup/v2-api): حزمة تجارية بتغطية لأكثر من 140 دولة، مع احتمال عدم توفر بيانات من بعض الشبكات.
- [Telesign Live Status](https://www.telesign.com/services): يصف ما إذا كان الرقم نشطًا أو قابلًا للوصول مع النوع وCarrier.
- [Vonage Number Insight](https://developer.vonage.com/de/api/number-insight?source=number-insight): Validity وReachability وRoaming.
- [CAMARA Device Reachability](https://github.com/camaraproject/DeviceStatus): مواصفات API مفتوحة للتحقق من اتصال الجهاز بالشبكة، لكن تنفيذها يحتاج مشغلًا داعمًا وموافقة مناسبة.

هذه الأدوات تغطي كذلك Current Carrier وLine Type وRoaming، لذلك تُنفذ من App Network Intelligence.

## النتيجة المقترحة

```text
line_status: live | dead | absent | unreachable | unknown | provider_blocked
reachability: reachable | temporarily_unreachable | not_reachable | unknown
network_response_code
provider
checked_at
expires_at
```

## قواعد القرار

- Timeout أو منع الاستعلام ← `unknown`، وليس `dead`.
- `absent` قد يكون مؤقتًا، ويحتاج Retry وفق تعريف المزود.
- `live` لا يعني أن صاحب الرقم وافق على التواصل.
- النتائج الحية قصيرة العمر ولا تستخدم إلى الأبد.
- لا نكرر فحوص الشبكة بصورة عدوانية.

## التوصية

هذه نقطة مدفوعة اختيارية تُستخدم للأرقام ذات القيمة الأعلى وبعد اجتياز الفحص المحلي. نختبر كل مزود على عينة معروفة قبل الاعتماد على تفسير حالاته.

## المصادر

- [HLR Lookup documentation](https://www.hlrlookup.com/docs/hlrlookup-docs.html)
- [Twilio Lookup v2 data packages](https://www.twilio.com/docs/lookup/v2-api)
- [CAMARA DeviceStatus](https://github.com/camaraproject/DeviceStatus)

