# 08 — إمكانية استقبال SMS

## السؤال

هل يمكن للرقم استقبال رسالة SMS؟

## مستويات الإثبات

1. **توقع محلي:** نوع الرقم Mobile أو Fixed-line قابل للرسائل في بعض الدول.
2. **مؤشر شبكة:** HLR/Carrier يقول إن الخط حي ونوعه مناسب.
3. **Delivery receipt:** بوابة الرسائل تبلغ أن الشبكة استلمت الرسالة، وليس بالضرورة أن المستخدم قرأها.
4. **OTP ناجح:** المستخدم استلم الرمز وأعاده؛ وهذا إثبات ملكية قوي وقت العملية.

## الأدوات والخدمات

- libphonenumber يساعد في استبعاد الأنواع غير المناسبة، لكنه لا يجرب التسليم.
- [HLR Lookup](https://www.hlrlookup.com/docs/hlrlookup-docs.html) يجمع Live Status وLine Type وCarrier.
- [Twilio Verify](https://www.twilio.com/docs/verify/api/verification) يدعم SMS وVoice وWhatsApp وSilent Network Auth.
- [Vonage Verify](https://developer.vonage.com/en/api/verify.v2) يدعم workflows عبر SMS وWhatsApp وVoice وSilent Auth.
- [CAMARA OTP Validation](https://github.com/camaraproject/OTPValidation/blob/main/code/API_definitions/one-time-password-sms.yaml) مواصفة مفتوحة لإرسال OTP والتحقق منه عبر المشغل.
- [TextBee](https://github.com/textbee/textbee) و[SMSKIT](https://github.com/smskit/smskit) بوابات SMS مفتوحة المصدر تستخدم هاتف Android وSIM كمرحل؛ لكنها لا تجعل تكلفة الشبكة صفرًا ولا تناسب الفحص الصامت الجماعي.

## النتيجة المقترحة

```text
sms_capability: likely | unlikely | unknown
sms_delivery_status: not_tested | submitted | delivered_to_network | failed | unknown
sms_ownership_status: unverified | otp_pending | otp_verified | otp_failed
```

## قواعد القرار

- لا نرسل رسالة لمجرد تنظيف قاعدة بيانات دون سبب وموافقة.
- `line_type=mobile` لا يساوي `sms_delivered`.
- `delivered` لا يساوي `read`.
- فقط إدخال OTP الصحيح يثبت الوصول الفعلي والملكية في تلك اللحظة.
- يجب وضع حدود للمحاولات لمنع SMS pumping والتكلفة غير المقصودة.

## التوصية

لبيانات الـCrawl نكتفي بـ`likely/unknown` من النوع وحالة الخط. نفعل OTP فقط عندما يشارك صاحب الرقم في عملية تحقق فعلية.

## المصادر

- [Twilio Verify](https://www.twilio.com/docs/verify/api/verification)
- [CAMARA OTP Validation](https://github.com/camaraproject/OTPValidation/blob/main/code/API_definitions/one-time-password-sms.yaml)
- [Vonage Verify API](https://developer.vonage.com/en/api/verify.v2)

