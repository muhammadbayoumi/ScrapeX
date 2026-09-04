# 14 — سمعة Spam وScam

## السؤال

هل توجد بلاغات أو مؤشرات أن الرقم يستخدم في مكالمات مزعجة أو احتيال أو إساءة؟

## ما الذي تثبته؟

تثبت وجود بلاغات أو إشارات مخاطرة مرتبطة بالرقم، لا أن كل اتصال منه احتيالي. يمكن انتحال Caller ID، وقد يعاد تخصيص الرقم لشخص جديد، وقد تكون البلاغات متحيزة أو خاطئة.

## الأدوات والمصادر

- [PhoneBlock](https://github.com/haumacher/phoneblock): مشروع مفتوح المصدر وقاعدة بلاغات مجتمعية مع API وقوائم حظر؛ فائدته تعتمد على التغطية الإقليمية.
- [CallShield](https://github.com/SysAdminDoc/CallShield): تطبيق مفتوح يجمع استعلامات من PhoneBlock ومصادر أخرى؛ يصلح كمرجع للتكامل وليس مصدرًا عالميًا نهائيًا.
- [IPQS](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview): يقدم Fraud Score وRecent Abuse وSpammer وRisk وSMS Pumping ضمن خدمة تجارية.
- [Telesign Intelligence](https://www.telesign.com/developer): محرك مخاطر يعتمد على إشارات هاتف وIP وبريد وسلوك.
- [Twilio Lookup](https://www.twilio.com/docs/lookup/v2-api): يقدم SMS Pumping Risk وPhone Number Quality Score ضمن حزم اختيارية.
- Truecaller/Getcontact يقدمان بلاغات جماعية داخل منتجاتهما، لكن لا يوجد مصدر بيانات مفتوح عام يمكن الاعتماد عليه دون شروطهما.

## النتيجة المقترحة

```text
reputation_signals[]:
  - source
  - label: spam | scam | telemarketing | robocall | sms_pumping | unknown
  - score
  - report_count
  - first_seen
  - last_seen
spam_risk: low | medium | high | unknown
```

## قواعد القرار

- لا ننشئ حكمًا نهائيًا من بلاغ واحد.
- نخفض وزن البلاغات القديمة بعد احتمال إعادة تخصيص الرقم.
- نميز البلاغ الجماعي عن إشارة شبكة أو نموذج احتيال تجاري.
- عدم وجود بلاغات لا يعني أن الرقم آمن.
- نحفظ مصدر كل Score ولا نخلط مقاييس مزودين مختلفين مباشرة.

## التوصية

نبدأ بـPhoneBlock كمصدر مفتوح تجريبي، ونضيف IPQS أو Telesign فقط إذا أثبتت الاختبارات قيمة إضافية. يبقى Risk App منفصلًا عن Validity حتى لا يصبح الرقم «غير صالح» لمجرد وجود بلاغ.

## المصادر

- [PhoneBlock](https://github.com/haumacher/phoneblock)
- [IPQS Phone Validation](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview)
- [Twilio Lookup v2](https://www.twilio.com/docs/lookup/v2-api)

