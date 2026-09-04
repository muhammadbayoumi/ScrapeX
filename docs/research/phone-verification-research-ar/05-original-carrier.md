# 05 — شركة الاتصالات الأصلية

## السؤال

ما الشركة التي خُصص لها نطاق الرقم في الأصل؟

## ما الذي تثبته؟

تثبت علاقة مقدمة الرقم بنطاق مخصص تاريخيًا لشركة اتصالات. لا تثبت أن الرقم ما زال على الشبكة نفسها؛ إذ يمكن نقله عبر Mobile Number Portability.

## الأدوات

- [Google libphonenumber](https://github.com/google/libphonenumber) يوفر `PhoneNumberToCarrierMapper`، ويذكر بوضوح أنه يعيد الشركة الأصلية لا الحالية.
- [python-phonenumbers](https://github.com/daviddrysdale/python-phonenumbers) يوفر منفذًا للوظيفة نفسها.
- [PhoneInfoga](https://github.com/sundowndev/PhoneInfoga) يعرض بيانات Carrier من مصادر محلية أو خارجية حسب الإعداد.
- [HLR Lookup](https://www.hlrlookup.com/docs/hlrlookup-docs.html) يعيد `originalNetworkDetails` إلى جانب الشبكة الحالية.
- Twilio وVonage وTelesign قد يعيدون Carrier ضمن حزم تغطي أيضًا النوع والحالة والمخاطر.

## النتيجة المقترحة

```text
original_carrier_name
original_mcc
original_mnc
carrier_basis: prefix_metadata | provider_database
carrier_metadata_version
```

## قواعد القرار

- نستخدم الاسم `original_carrier` دائمًا، وليس `carrier` فقط.
- عدم وجود اسم لا يجعل الرقم غير صالح.
- عند توفر Current Carrier نخزن الاثنين ولا نستبدل أحدهما بالآخر.
- metadata المحلية تحتاج تحديثًا دوريًا.

## التوصية

هذه معلومة مجانية ومفيدة للفرز الأولي، لكنها لا تكفي لمسار الرسائل أو الحكم على الشبكة الحالية. عند الحاجة إلى الشبكة الفعلية ننتقل للنقطة 6 باستخدام MNP/HLR.

## المصادر

- [Google libphonenumber carrier caveat](https://github.com/google/libphonenumber)
- [HLR Lookup fields](https://www.hlrlookup.com/docs/hlrlookup-docs.html)

