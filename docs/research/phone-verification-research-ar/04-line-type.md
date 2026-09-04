# 04 — نوع الخط

## السؤال

هل الرقم Mobile أو Landline أو VoIP أو Toll-free أو Premium-rate أو نوعًا آخر؟

## ما الذي تثبته؟

تساعد معرفة النوع في اختيار قناة التواصل وتقدير المخاطر، لكنها لا تثبت أن الخط حي. النوع المبني على metadata قد يتغير أو يكون غامضًا، خصوصًا مع نقل الأرقام وVoIP.

## الأدوات

- [Google libphonenumber](https://github.com/google/libphonenumber) يميز، متى توفرت البيانات، بين Fixed-line وMobile وToll-free وPremium وShared-cost وVoIP وPager وغيرها.
- [libphonenumber-js](https://github.com/catamphetamine/libphonenumber-js/blob/master/README.md) يوفر `getType()`، مع ضرورة استخدام `max` metadata للدقة الأفضل.
- [HLR Lookup](https://www.hlrlookup.com/docs/hlrlookup-docs.html) يعيد نوع الخط ضمن فحص مدفوع أو Validation مجاني حسب الخدمة.
- [Twilio Line Type Intelligence](https://www.twilio.com/docs/lookup/v2-api) و[IPQS](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview) و[Telesign Phone ID](https://developer.telesign.com/enterprise/docs/phone-id-get-started) تجمع النوع مع Carrier وRisk.

## النتيجة المقترحة

```text
line_type: mobile | fixed_line | fixed_or_mobile | voip_fixed | voip_non_fixed |
           toll_free | premium | shared_cost | pager | uan | voicemail | unknown
line_type_source
line_type_confidence
```

## قواعد القرار

- لا نخلط `fixed_or_mobile` مع `mobile`.
- VoIP ليس بالضرورة احتياليًا؛ هو إشارة تحتاج سياقًا.
- Toll-free وPremium وShared-cost ليست عناوين شخصية عادية.
- إذا تعارضت metadata مع مزود حي، نحفظ النتيجتين ويكون للمصدر الحي وزن أعلى مع تاريخ صلاحية أقصر.

## التوصية

ننفذ كشفًا أوليًا مجانيًا باستخدام libphonenumber، ثم نطلب Line Type مدفوعًا فقط للأرقام التي تحتاج قرارًا أدق أو ترتبط بمخاطر أعلى.

## المصادر

- [Google libphonenumber](https://github.com/google/libphonenumber)
- [Twilio Lookup data packages](https://www.twilio.com/docs/lookup/v2-api)
- [IPQS Phone Validation](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview)

