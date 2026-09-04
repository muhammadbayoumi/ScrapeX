# 12 — الاسم المرتبط بالرقم

## السؤال

هل يمكن معرفة اسم شخص أو شركة مرتبط بالرقم مثل Truecaller أو Getcontact؟

## ما الذي تثبته؟

غالبًا تعطي الخدمات اسمًا جماعيًا أو اسم فاتورة أو CNAM أو اسمًا قدمه المستخدم. لا يُعامل أي منها تلقائيًا كهوية قانونية، وقد يكون قديمًا أو خاطئًا أو يخص مالكًا سابقًا.

## المصادر والأدوات

- [Truecaller SDK](https://docs.truecaller.com/truecaller-sdk): يتيح التحقق ومشاركة ملف مستخدم Truecaller بعد موافقته. ليس قاعدة مفتوحة لتحميل أسماء الأرقام تعسفيًا.
- [Getcontact Number Lookup](https://getcontact.com/features): متاح كميزة في المنتج، لكن لم يظهر في المراجعة الحالية API عام رسمي للبحث الآلي الخارجي.
- [Twilio Caller Name](https://www.twilio.com/docs/lookup/v2-api): حزمة Caller Name مذكورة بتغطية أرقام الولايات المتحدة فقط.
- [Telesign Phone ID](https://www.telesign.com/products/phone-id): يوفر Contact وContact Match وSubscriber attributes حسب الدولة والتعاقد.
- [IPQS Phone Validation](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview): قد يعيد اسم شخص أو شركة مع Validity وCarrier وRisk.
- [CAMARA KYC Match](https://github.com/camaraproject/KnowYourCustomer/blob/main/code/API_definitions/kyc-match.yaml): مواصفة مفتوحة لمطابقة اسم أو صفات يقدمها المستخدم مع بيانات المشغل، لا لإرجاع اسم شخص مجهول.

لا توجد قاعدة أسماء عالمية مفتوحة المصدر يمكنها منافسة Truecaller؛ القيمة هنا في البيانات المملوكة والمجمعة، لا في الكود فقط.

## النتيجة المقترحة

```text
caller_labels[]:
  - value
  - label_type: crowdsourced | cnam | carrier_subscriber | business_public | user_supplied
  - source
  - confidence
  - observed_at
verified_legal_name: null
```

## قواعد القرار

- لا نخزن حقلًا واحدًا اسمه `owner_name`.
- نحتفظ بعدة Labels مع المصدر والتاريخ.
- الاسم القادم من صفحة الشركة الرسمية أقوى للهوية التجارية من اسم جماعي.
- اختلاف الأسماء قد يدل على رقم مشترك أو إعادة تخصيص أو بيانات رديئة.
- لا نستخدم APIs غير رسمية تستخرج Tokens من Truecaller/Getcontact.

## التوصية

نبني Name Enrichment كـAdapter متعدد المصادر، ونسمّي النتائج `caller_labels`. Truecaller الرسمي يستخدم فقط في تدفق موافقة، ومصادر الـCrawl الرسمية لها أولوية في إثبات هوية الشركات.

## المصادر

- [Truecaller SDK](https://docs.truecaller.com/truecaller-sdk)
- [Truecaller consent requirement](https://developer.truecaller.com/Truecaller-sdk-product-license-agreement-RoW.pdf)
- [Twilio Lookup v2](https://www.twilio.com/docs/lookup/v2-api)
- [CAMARA KYC Match](https://github.com/camaraproject/KnowYourCustomer/blob/main/code/API_definitions/kyc-match.yaml)

