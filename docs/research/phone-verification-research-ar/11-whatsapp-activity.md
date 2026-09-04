# 11 — نشاط حساب واتساب

## السؤال

هل صاحب الرقم يستخدم واتساب حاليًا أو يقرأ الرسائل؟

## الإجابة الواقعية

لا توجد طريقة موثوقة ومشروعة لتحويل وجود الحساب إلى قياس نشاط صامت. التسجيل على واتساب لا يعني أن التطبيق ما زال مستخدمًا، وظهور Last Seen أو الصورة أو الحالة يخضع لإعدادات الخصوصية وقد يكون مخفيًا.

## الأدلة الممكنة

- `registered`: يثبت وجود الحساب فقط.
- رسالة أرسلها المستخدم إلينا: دليل مباشر على نشاطه في ذلك الوقت.
- Delivery receipt لرسالة مصرح بها: يدل على وصول الرسالة إلى جهاز أو حساب، لا على قراءة الشخص لها.
- Read receipt: يعتمد على الإعدادات والسياق، ولا ينبغي استخدامه كبيانات إثراء عامة.
- OTP ناجح عبر واتساب: يثبت الوصول إلى الحساب أثناء عملية التحقق.

## الأدوات

- [whatsmeow](https://github.com/tulir/whatsmeow) و[whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js) و[Baileys](https://github.com/WhiskeySockets/Baileys) تستطيع إدارة رسائل وإيصالات عبر جلسة مرتبطة، لكنها غير رسمية ولا ينبغي استخدامها لمراقبة Last Seen أو الملف الشخصي.
- [Twilio Verify](https://www.twilio.com/docs/verify/api/verification) و[Vonage Verify](https://developer.vonage.com/en/api/verify.v2) يقدمان WhatsApp OTP ضمن تدفق مصرح به.

الأدوات نفسها تغطي النقطة 10 لوجود الحساب والنقطة 19 لإثبات الملكية، لكن هذه النقطة يجب ألا تتحول إلى App مراقبة.

## النتيجة المقترحة

```text
whatsapp_presence: registered | not_registered | unknown
whatsapp_interaction: none | inbound_message | authorized_delivery | otp_verified
last_authorized_interaction_at
activity_claim: not_inferred
```

## قواعد القرار

- لا نخزن Last Seen أو الصورة أو About لأغراض تقييم النشاط.
- لا نفسر إخفاء Read Receipts كعدم نشاط.
- لا نرسل رسالة اختبار دون موافقة.
- أفضل دليل هو تفاعل بدأه المستخدم أو OTP مصرح به.
- واتساب يحظر الجمع الآلي غير المصرح به للمعلومات الشخصية. راجع [سياسته الرسمية](https://faq.whatsapp.com/434518851968943).

## التوصية

لا نبني «WhatsApp Activity Scanner». نكتفي بوجود الحساب في النقطة 10، ونسجل التفاعلات المصرح بها فقط عند حدوثها.

## المصادر

- [WhatsApp: About harvesting personal information](https://faq.whatsapp.com/434518851968943)
- [Twilio Verify channels](https://www.twilio.com/docs/verify/authentication-channels?display=embedded)

