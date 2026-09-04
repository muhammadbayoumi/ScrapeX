# 13 — هوية الشركة أو النشاط التجاري

## السؤال

هل الرقم منشور رسميًا لشركة أو نشاط، وما اسم الجهة ودور الرقم؟

## ما الذي تثبته؟

عندما يظهر الرقم على الموقع الرسمي للشركة أو داخل بيانات منظمة مرتبطة بالدومين نفسه، يمكن اعتباره دليلًا جيدًا على علاقة الرقم بالنشاط. ظهوره في دليل طرف ثالث أو منشور قديم أضعف ويحتاج أكثر من مصدر.

## الأدوات والمصادر

- بيانات الـCrawl نفسها: الصفحة، العنوان، اسم الموقع، الرابط، والنص المحيط بالرقم.
- [Schema.org telephone](https://schema.org/telephone): يمكن استخراج أرقام `Organization` و`ContactPoint` من JSON-LD أو Microdata.
- [PhoneInfoga](https://github.com/sundowndev/PhoneInfoga): يساعد في OSINT والبحث عن آثار الرقم العامة، لكنه لا يثبت الملكية.
- [SpiderFoot](https://spiderfoot.org/): إطار OSINT مفتوح المصدر لربط الأدلة العامة، يستخدم بحذر وضمن نطاق مصرح.
- OpenStreetMap قد يحتوي أرقام الأنشطة، لكن خدمة Nominatim العامة تمنع الاستخدام الكثيف والمنهجي وتفرض حدودًا وشروط Attribution؛ راجع [سياسة Nominatim](https://operations.osmfoundation.org/policies/nominatim/).
- Caller-name providers مثل Telesign وIPQS قد يعيدون اسم شركة، ويجب حفظه كمصدر منفصل.

هذه النقطة تجمع بين أدوات الـCrawler الموجودة، PhoneInfoga، Schema.org، والاسم من النقطة 12.

## نموذج الدليل

```text
business_matches[]:
  - organization_name
  - phone_role: sales | support | main | billing | whatsapp | unknown
  - source_url
  - source_type: official_site | structured_data | public_directory | provider
  - same_domain_as_crawl
  - observed_at
  - confidence
```

## قواعد القرار

- مصدر رسمي حديث على نفس الدومين له أعلى وزن.
- دليل طرف ثالث وحده لا يكفي لحسم الملكية.
- نميز رقم الشركة العام عن رقم موظف شخصي.
- نحتفظ بالنص المحيط بالرقم لأنه يوضح الوظيفة واللغة والفرع.
- إذا اختفى الرقم من الموقع الرسمي لا نحذفه فورًا؛ يصبح `stale` ويعاد تقييمه.

## التوصية

هذه من أكثر النقاط قيمة للأداة الحالية لأنها تستفيد من سياق الـCrawl الذي لا تملكه خدمات Lookup. نطورها قبل شراء خدمات أسماء باهظة، مع إبقاء التفاصيل التقنية لمرحلة فحص الريبو.

## المصادر

- [Schema.org telephone](https://schema.org/telephone)
- [Schema.org Organization](https://schema.org/Organization)
- [PhoneInfoga](https://github.com/sundowndev/PhoneInfoga)
- [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)

