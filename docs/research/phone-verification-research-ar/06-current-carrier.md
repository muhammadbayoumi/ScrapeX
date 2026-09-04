# 06 — شركة الاتصالات الحالية

## السؤال

على أي شبكة يعمل الرقم الآن بعد احتساب نقل الأرقام بين الشركات؟

## ما الذي تثبته؟

تعطي أفضل تقدير متاح للشبكة التي تستضيف الرقم وقت الفحص. تختلف الدقة والتغطية حسب الدولة ومصدر MNP/HLR، وقد تكون النتيجة Cached أو غير متاحة.

## الأدوات والخدمات

- [HLR Lookup SDK](https://github.com/hlrlookup-com/hlrlookup-php-sdk): SDK مفتوح المصدر يعيد `currentNetworkDetails`، لكن الخدمة الخلفية مدفوعة.
- [Twilio Line Type Intelligence](https://www.twilio.com/docs/lookup/v2-api): يمكن أن يعيد اسم Carrier وMCC/MNC ضمن حزمة تجارية.
- [Vonage Identity Insights](https://developer.vonage.com/de/api/number-insight?source=number-insight): يجمع Current وOriginal Carrier مع إشارات أخرى.
- [Telesign Phone ID](https://developer.telesign.com/enterprise/docs/phone-id-get-started): Carrier وPhone Type وبيانات إضافية حسب التغطية.
- [IPQS](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview): يجمع Carrier والحالة والنوع والمخاطر.

كل هذه الأدوات تغطي أكثر من هذه النقطة؛ لذلك تُربط من خلال App واحد اسمه Network Intelligence، وليس App منفصلًا لكل Provider.

## لماذا لا يكفي Open Source؟

الكود يمكن أن يكون مفتوحًا، لكن MNP وHLR يعتمدان على بيانات واتصالات المشغلين. لذلك لا توجد قاعدة عالمية مفتوحة ومحدثة يمكنها إعطاء الشبكة الحالية لجميع الأرقام مجانًا.

## النتيجة المقترحة

```text
current_carrier_name
current_mcc
current_mnc
current_network_country
carrier_status: resolved | unavailable | conflicting | stale
provider
checked_at
```

## قواعد القرار

- لا نستبدل Original Carrier بالـCurrent Carrier.
- نتيجة `unavailable` ليست خطأ في الرقم.
- عند تعارض مزودين نخزن الدليلين ولا نختار بالتصويت فقط.
- تُحدد مدة صلاحية قصيرة نسبيًا لأن الرقم يمكن نقله لاحقًا.

## التوصية

نبدأ بـAdapter واحد لـHLR/MNP بعد اختبار التغطية على الدول المهمة، ثم نضيف مزودًا ثانيًا فقط للحالات غير المعروفة أو للمقارنة، لتقليل التكلفة.

## المصادر

- [HLR Lookup SDK](https://github.com/hlrlookup-com/hlrlookup-php-sdk)
- [Twilio Lookup v2](https://www.twilio.com/docs/lookup/v2-api)
- [Vonage Number/Identity Insights](https://developer.vonage.com/de/api/number-insight?source=number-insight)

