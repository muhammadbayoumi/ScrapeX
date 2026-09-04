# 09 — إمكانية استقبال المكالمات

## السؤال

هل الرقم قادر على استقبال مكالمة صوتية، وهل يمكن إثبات أن شخصًا استلمها؟

## مستويات الإثبات

- نوع الخط يوحي بأنه يدعم Voice.
- Line Status يشير إلى أن الخط حي.
- نتيجة المكالمة تفرق بين Answered وBusy وNo Answer وFailed.
- Voice OTP ناجح يثبت أن شخصًا لديه وصول للخط، لكنه لا يثبت هويته القانونية.

## الأدوات والخدمات

- libphonenumber يحدد Mobile/Landline/VoIP/Toll-free، دون إجراء مكالمة.
- HLR وTelesign وVonage قد يعطون Reachability ونوع الخط.
- [Twilio Verify](https://www.twilio.com/en-us/user-authentication-identity/verify) يدعم Voice OTP ويمكن استخدامه كـFallback بعد SMS.
- [Vonage Verify](https://www.vonage.com/communications-apis/verify/) يدعم Voice TTS إلى جانب SMS وWhatsApp وSilent Authentication.
- منصات الاتصال المفتوحة مثل Asterisk يمكنها تنفيذ مكالمات، لكنها تحتاج SIP trunk مدفوعًا وإدارة قانونية وتشغيلية؛ وليست قاعدة تحقق في حد ذاتها.

الأدوات التجارية هنا تغطي أيضًا SMS وOwnership Verification، ولذلك توضع خلف Adapter موحد اسمه Verification Provider.

## النتيجة المقترحة

```text
voice_capability: likely | unlikely | unknown
call_test_status: not_tested | answered | busy | no_answer | rejected | failed | unknown
voice_ownership_status: unverified | otp_verified | otp_failed
```

## حدود مهمة

- مكالمة دون رد لا تعني أن الرقم غير موجود.
- الرد الآلي أو البريد الصوتي لا يثبت وجود صاحب الرقم.
- إجراء مكالمات تلقائية على أرقام مكتشفة بالـCrawl قد يكون مزعجًا أو مخالفًا للقواعد المحلية.
- لا يجرى Voice OTP إلا ضمن تجربة يبدأها المستخدم أو يوافق عليها.

## التوصية

لا نجعل الاتصال الصوتي جزءًا من التنظيف الصامت. نستخدم Line Type وLine Status كمؤشرات، وVoice OTP كخيار إثبات ملكية عند فشل SMS أو بطلب المستخدم.

## المصادر

- [Twilio Verify channels](https://www.twilio.com/docs/verify/authentication-channels?display=embedded)
- [Vonage Verify](https://www.vonage.com/communications-apis/verify/)

