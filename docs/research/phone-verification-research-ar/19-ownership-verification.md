# 19 — إثبات ملكية الرقم

## السؤال

هل الشخص الذي يتفاعل مع النظام يملك وصولًا فعليًا إلى الرقم الآن؟

## طرق الإثبات

| الطريقة | قوة الدليل | القيود |
|---|---|---|
| SMS OTP | قوية لامتلاك الوصول وقت العملية | SIM swap، اعتراض SMS، تكلفة، تغطية |
| Voice OTP | قوية عند نجاح إدخال الرمز | رد آلي، تكلفة، إزعاج إذا لم يبدأه المستخدم |
| WhatsApp OTP | يثبت الوصول إلى حساب واتساب | يحتاج قناة رسمية وسياسات WhatsApp |
| Silent Network Authentication | قوية ومريحة | تعتمد على مشغل وشبكة وجهاز مدعوم |
| CAMARA Number Verification | يطابق الرقم مع SIM/اتصال الجهاز | يحتاج مزودًا داعمًا وتفويض المستخدم |

## الأدوات والخدمات

- [Twilio Verify](https://www.twilio.com/docs/verify/api/verification): SMS وVoice وWhatsApp وSilent Network Auth.
- [Vonage Verify](https://developer.vonage.com/en/api/verify.v2): Workflows متعددة القنوات وSilent Auth.
- [CAMARA Number Verification](https://github.com/camaraproject/NumberVerification/blob/main/code/API_definitions/number-verification.yaml): مواصفة مفتوحة للتحقق الصامت من الرقم المرتبط بـSIM المستخدمة للوصول إلى التطبيق.
- [CAMARA OTP Validation](https://github.com/camaraproject/OTPValidation/blob/main/code/API_definitions/one-time-password-sms.yaml): إرسال OTP والتحقق منه كإثبات حيازة.
- [TextBee](https://github.com/textbee/textbee) و[SMSKIT](https://github.com/smskit/smskit): بوابات ذاتية الاستضافة باستخدام هاتف Android؛ توفر الإرسال لا الثقة الأمنية الكاملة، وتبقى تكلفة SIM وسياسات المشغل.

هذه الخدمات تغطي أيضًا SMS وVoice وWhatsApp، لذلك يكفي Adapter واحد متعدد القنوات بدل App منفصل لكل قناة.

## النتيجة المقترحة

```text
ownership_status: unverified | pending | verified | failed | expired
verification_channel: sms | voice | whatsapp | silent_network
verified_at
verification_context
provider
```

## قواعد القرار

- لا يرسل OTP إلى رقم تم جمعه بالـCrawl دون أن يبدأ صاحبه العملية.
- نضع Rate limits وحدود محاولات ومراقبة SMS pumping.
- نجاح OTP يثبت الوصول وليس الاسم أو الهوية القانونية.
- إثبات الملكية مرتبط بسياق وزمن، وقد يحتاج إعادة تحقق بعد تغيير SIM أو إعادة تخصيص.
- لا نخزن OTP نفسه بعد انتهاء العملية.

## التوصية

هذه أقوى طبقة لكنها ليست أداة تنظيف صامتة. تُبنى فقط عند وجود تدفق يشارك فيه صاحب الرقم، وتظل منفصلة عن Validity وReachability.

## المصادر

- [Twilio Verify API](https://www.twilio.com/docs/verify/api/verification)
- [CAMARA Number Verification](https://github.com/camaraproject/NumberVerification/blob/main/code/API_definitions/number-verification.yaml)
- [CAMARA OTP Validation](https://github.com/camaraproject/OTPValidation/blob/main/code/API_definitions/one-time-password-sms.yaml)

