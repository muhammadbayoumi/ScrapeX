# 20 — الموافقة على التواصل

## السؤال

هل وجود الرقم في قاعدة البيانات يعني أن لدينا حقًا أو موافقة للتواصل معه؟

## الإجابة

لا. استخراج الرقم من صفحة عامة، وصحته، ووجود واتساب، وحتى معرفة اسم صاحبه لا تعني موافقته على الرسائل أو المكالمات. Consent بُعد مستقل يجب تسجيل مصدره ونطاقه وتاريخه.

## مصادر الموافقة الممكنة

- نموذج ملأه صاحب الرقم مع نص موافقة واضح.
- طلب تواصل بدأه الشخص.
- علاقة تعاقدية أو غرض مشروع يسمح به القانون المطبق.
- اشتراك محدد القناة والغرض.
- قائمة إلغاء أو رفض يجب احترامها.

## الأدوات المرتبطة

- النظام الداخلي هو المصدر الأساسي لسجل Consent.
- [Truecaller SDK](https://developer.truecaller.com/Truecaller-sdk-product-license-agreement-RoW.pdf) يشترط موافقة صريحة ومستنيرة قبل جمع بيانات المستخدم عبر SDK.
- واتساب يوصي بالتواصل مع من طلب الاتصال واحترام الحدود، ويحذر من استخدام قوائم لا يملكها المستخدم أو إرسال رسائل غير مرغوبة. راجع [إرشادات الاستخدام المسؤول](https://faq.whatsapp.com/general/security-and-privacy/how-to-use-whatsapp-responsibly?category=5245250&lang=fil).
- [IPQS](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview) قد يعيد DNC/TCPA indicators لبعض الأسواق، لكنها ليست بديلًا عن سجل الموافقة والقانون المحلي.

## النتيجة المقترحة

```text
consent_status: granted | denied | withdrawn | unknown | not_required_for_purpose
consent_channels[]: sms | voice | whatsapp
consent_purpose
consent_source
consent_text_version
granted_at
withdrawn_at
jurisdiction
```

## قواعد القرار

- `publicly_listed` ليست حالة Consent.
- موافقة SMS لا تمنح تلقائيًا موافقة WhatsApp أو المكالمات.
- سحب الموافقة له أولوية على أي نتيجة تحقق فنية.
- المتطلبات تختلف حسب الدولة والغرض؛ يحتاج التنفيذ مراجعة القواعد المحلية وقتها.
- يحتفظ بالدليل الضروري فقط، مع سياسات وصول وحذف واضحة.

## التوصية

نجعل Consent Gate قبل أي عملية إرسال، لكنه لا يمنع حفظ الرقم كمعلومة عامة موثقة إذا كان جمعه واستخدامه مشروعين. هذا الملف تنظيمي وليس رأيًا قانونيًا.

## المصادر

- [WhatsApp responsible use](https://faq.whatsapp.com/general/security-and-privacy/how-to-use-whatsapp-responsibly?category=5245250&lang=fil)
- [Truecaller SDK consent terms](https://developer.truecaller.com/Truecaller-sdk-product-license-agreement-RoW.pdf)

