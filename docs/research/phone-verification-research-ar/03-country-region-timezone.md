# 03 — الدولة والمنطقة والتوقيت

## السؤال

ما الدولة أو المنطقة العامة والتوقيتات المحتملة المرتبطة بمقدمة الرقم؟

## ما الذي تثبته؟

تعطي دلالة جغرافية لخطة الترقيم، لا موقع الجهاز الحالي. أرقام الهاتف المحمول، نقل الأرقام، التجوال، وVoIP تجعل الاستنتاج أقل دقة.

## الأدوات

- [Google libphonenumber](https://github.com/google/libphonenumber) يوفر Offline Geocoder وTime Zone Mapper.
- [python-phonenumbers](https://github.com/daviddrysdale/python-phonenumbers) يقدم الوظائف نفسها في Python.
- [PhoneInfoga](https://github.com/sundowndev/PhoneInfoga) يجمع بيانات المنطقة ومصادر OSINT العامة.
- [Telesign Phone ID](https://developer.telesign.com/enterprise/docs/phone-id-get-started) و[IPQS](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview) يعيدان بيانات موقع/منطقة ضمن خدمات تجارية أوسع.

هذه الأدوات تغطي كذلك التنسيق والنوع والشركة، لذلك لا نحتاج App مستقلًا لهذه النقطة؛ تكون جزءًا من Phone Basics وNetwork Intelligence.

## النتيجة المقترحة

```text
country_code
country_calling_code
region_hint
timezone_hints[]
geo_confidence: high | medium | low | none
geo_basis: numbering_plan | carrier_data | public_business_source
```

## حدود الدقة

- لا نكتب `current_location` بناءً على مقدمة الرقم.
- بعض الدول تستخدم كود اتصال مشتركًا.
- رقم المحمول لا يدل بالضرورة على مدينة.
- وجود المستخدم في Roaming لا يغير الدولة الأصلية للرقم.
- المنطقة المستخرجة من مصدر تجاري عام يجب حفظ مصدرها وتاريخها.

## التوصية

نستخدمها للتنسيق، اللغة، التوقيت المتوقع، وفهم المصدر؛ ولا نعرضها كتعقب أو موقع حالي. أي بيانات Roaming أو موقع شبكة مباشر تُحفظ في حقل منفصل وبصلاحيات أعلى.

## المصادر

- [Google libphonenumber features](https://github.com/google/libphonenumber)
- [Telesign Phone ID](https://developer.telesign.com/enterprise/docs/phone-id-get-started)

