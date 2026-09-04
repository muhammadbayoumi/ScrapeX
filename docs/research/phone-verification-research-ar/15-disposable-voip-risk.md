# 15 — VoIP والأرقام المؤقتة

## السؤال

هل الرقم VoIP أو افتراضي أو مؤقت أو Burner، وهل يرفع ذلك مستوى المخاطرة؟

## ما الذي تثبته؟

تحديد Line Type أو مزود VoIP يعطي إشارة عن طبيعة الرقم. لا يثبت وحده الاحتيال؛ شركات ومستخدمون شرعيون يعتمدون VoIP، كما أن Prepaid ليس مرادفًا لرقم مؤقت.

## الأدوات

- [Google libphonenumber](https://github.com/google/libphonenumber) يستطيع تصنيف VoIP أو Mobile أو Fixed-line عندما تسمح metadata.
- [Twilio Line Type Intelligence](https://www.twilio.com/docs/lookup/v2-api) يفرق بين Fixed VoIP وNon-fixed VoIP وأنواع أخرى.
- [HLR Lookup](https://www.hlrlookup.com/docs/hlrlookup-docs.html) يعيد نوع الرقم وحقلًا للأرقام المؤقتة حسب الخدمة.
- [IPQS](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview) يعيد VOIP وPrepaid وRisk وFraud Score وActive Status.
- [Telesign Phone ID](https://www.telesign.com/products/phone-id) يجمع نوع الهاتف وCarrier وRisk attributes.

الأدوات السابقة تغطي النقاط 4 و6 و7 و14 أيضًا، ولذلك لا نرسل الرقم إلى خدمة إضافية إذا كانت نتيجة Network Intelligence تحتوي هذه الحقول بالفعل.

## النتيجة المقترحة

```text
voip_status: fixed_voip | non_fixed_voip | not_voip | unknown
prepaid_status: yes | no | unknown
disposable_status: likely | unlikely | unknown
provider_name
risk_reasons[]
```

## قواعد القرار

- `voip=true` إشارة، وليس حكم رفض.
- Non-fixed VoIP عادة أعلى مخاطرة من Fixed VoIP، لكن القرار يعتمد على الحالة.
- `prepaid=true` لا يعني Disposable.
- نحتاج مصدرًا وتاريخًا لأن مزودي الأرقام يعيدون تدوير النطاقات.
- يمكن رفع مستوى الفحص أو طلب OTP بدل حذف الرقم.

## التوصية

نستخدم Line Type المحلي أولًا، ثم نستهلك هذه البيانات من مزود Network/Risk الموجود أصلًا. لا نشتري API منفصلة لمجرد حقل VoIP ما لم تُظهر التجربة فرقًا واضحًا.

## المصادر

- [Twilio Line Type Intelligence](https://www.twilio.com/docs/lookup/v2-api)
- [HLR Lookup fields](https://www.hlrlookup.com/docs/hlrlookup-docs.html)
- [IPQS Phone Validation](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview)

