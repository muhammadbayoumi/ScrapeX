# 10 — وجود حساب واتساب

## السؤال

هل الرقم مسجل على واتساب وقت الفحص؟

## ما الذي تثبته؟

تثبت، عند نجاح الاستعلام، أن واتساب يعرف الرقم كحساب مسجل في تلك اللحظة. لا تثبت أن المستخدم نشط، أو يقرأ الرسائل، أو ما زال المالك نفسه، أو وافق على التواصل.

## المشاريع المفتوحة المصدر

| المشروع | الوظيفة | الترخيص | الحالة |
|---|---|---:|---|
| [whatsmeow](https://github.com/tulir/whatsmeow) | عميل Go يحتوي على `IsOnWhatsApp` | MPL-2.0 | مرشح Pilot |
| [whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js) | `isRegisteredUser` و`getNumberId` | Apache-2.0 | مرشح Pilot |
| [Baileys](https://github.com/WhiskeySockets/Baileys) | عميل TypeScript/JavaScript لـWhatsApp Web | MIT | بديل غير رسمي |

هذه المشاريع مفتوحة المصدر، لكنها جميعًا تعتمد على بروتوكول أو جلسة WhatsApp Web غير رسمية. فتح الكود لا يجعل طريقة الاستخدام معتمدة من Meta.

## المسار الرسمي

WhatsApp Business Platform وموفرو Verify يدعمون الرسائل وOTP ضمن قنوات رسمية، لكن ذلك ليس Reverse Lookup صامتًا مفتوحًا لاختبار قوائم أرقام عشوائية. [Twilio Verify](https://www.twilio.com/docs/verify/api/verification) مثلًا يدعم قناة WhatsApp لإثبات الوصول عندما يشارك المستخدم في عملية تحقق.

## مخاطر الاستخدام

واتساب يصرح بأن جمع معلومات المستخدمين آليًا على نطاق واسع لأغراض غير مصرح بها يخالف شروطه، وقد يؤدي إلى تقييد الحساب أو حظره. راجع [سياسة جمع المعلومات](https://faq.whatsapp.com/434518851968943) و[الاستخدام الآلي والجماعي](https://faq.whatsapp.com/5957850900902049).

## النتيجة المقترحة

```text
whatsapp_status: registered | not_registered | unknown | rate_limited |
                 session_blocked | temporarily_unavailable | stale
provider: whatsmeow | whatsapp_web_js | baileys | official_verify
checked_at
expires_at
```

## قواعد القرار

- فشل الجلسة أو Timeout ← `unknown`، وليس `not_registered`.
- لا نجلب الصورة أو الحالة أو About أو بيانات شخصية إضافية.
- لا نرسل رسالة لمجرد الفحص.
- نحفظ Cache لتجنب الاستعلام المتكرر.
- يُستخدم فقط على أرقام مصرح بفحصها وبحدود صغيرة.
- تُعزل الجلسة المستخدمة، ويكون التطبيق اختياريًا ومغلقًا افتراضيًا.

## التوصية

نبني WhatsApp Presence كتطبيق تجريبي مستقل، لا كمرحلة إلزامية. يبدأ بـwhatsmeow أو whatsapp-web.js بعد اختبار محدود، مع إمكانية تعطيله فور تغير البروتوكول أو الشروط.

## المصادر

- [whatsmeow IsOnWhatsApp](https://github.com/tulir/whatsmeow/blob/main/user.go)
- [whatsapp-web.js types](https://github.com/pedroslopez/whatsapp-web.js/blob/main/index.d.ts)
- [WhatsApp harvesting policy](https://faq.whatsapp.com/434518851968943)

