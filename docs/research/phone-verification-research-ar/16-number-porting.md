# 16 — نقل الرقم بين الشبكات

## السؤال

هل نُقل الرقم من شركة الاتصالات الأصلية إلى شبكة أخرى، وما الشبكة الحالية؟

## ما الذي تثبته؟

تكشف MNP/Portability أن مقدمة الرقم لم تعد كافية لتحديد الشبكة الحالية. هذه المعلومة مهمة لتوجيه الرسائل، تفسير فشل HLR، واكتشاف تغيرات حديثة قد تستحق إعادة التحقق.

## الأدوات والخدمات

- [HLR Lookup SDK](https://github.com/hlrlookup-com/hlrlookup-php-sdk): يعيد `isPorted` وOriginal/Current Network، ويمكن طلب تاريخ النقل بتكلفة إضافية حسب الخدمة.
- [Twilio Lookup](https://www.twilio.com/docs/lookup/v2-api): Line Type وCarrier، مع إشارات أخرى حسب السوق.
- [Vonage Identity Insights](https://www.vonage.com/communications-apis/number-insight/features/): يجمع Current وOriginal Carrier وSIM Swap وSubscriber Match.
- [Telesign Phone ID](https://www.telesign.com/products/phone-id): قد يعيد Porting history وCarrier attributes حسب الباقة والتغطية.

SDKs قد تكون مفتوحة، لكن قواعد MNP الوطنية والوصول إلى المشغلين ليست قاعدة بيانات عالمية مفتوحة.

## النتيجة المقترحة

```text
ported_status: yes | no | unknown
original_carrier
current_carrier
ported_at: timestamp | unavailable
porting_source
checked_at
```

## قواعد القرار

- `ported=yes` لا يعني مخاطرة أو احتيالًا.
- النقل الحديث قد يرفع الحاجة إلى إعادة إثبات الملكية في المعاملات الحساسة.
- اختلاف الشركة الأصلية والحالية نتيجة طبيعية، لا تعارضًا.
- تاريخ النقل غير متوفر في جميع الدول أو لدى جميع المزودين.
- نعيد فحص الشبكة الحالية بعد مدة بدل الاعتماد على Cache دائم.

## التوصية

تكون Porting نتيجة فرعية من Network Intelligence، وليست API مستقلة. نطلب تاريخ النقل فقط للحالات التي تستفيد منه، لتقليل التكلفة.

## المصادر

- [HLR Lookup SDK](https://github.com/hlrlookup-com/hlrlookup-php-sdk)
- [Vonage Identity Insights features](https://www.vonage.com/communications-apis/number-insight/features/)
- [Telesign Phone ID](https://www.telesign.com/products/phone-id)

