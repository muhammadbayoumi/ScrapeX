# حزمة بحث التحقق من أرقام الهاتف

> **RESEARCH, NOT A PLAN AND NOT A TRACKING DOCUMENT.** Brought into the repo on
> 2026-09-04 unchanged. Nothing here is maintained against the code.
>
> The eight apps below are issues in milestone **#6 · Phone verification: evidence,
> never a single valid/invalid**. Two of them — Network Intelligence and Ownership
> Verification — have no open-source path and need a paid provider; the WhatsApp
> Presence app carries a stated terms-of-service risk. Those are the owner's calls and
> are recorded as such. The plan waits on milestone **#8**.

آخر مراجعة: 4 سبتمبر 2026

## الهدف

هذه الحزمة تحصر طبقات التحقق من أرقام الهاتف المكتشفة بعد الـCrawl. لكل نقطة ملف مستقل يوضح ما يمكن إثباته، وما لا يمكن إثباته، والأدوات المفتوحة المصدر والخدمات الخارجية، وشكل النتيجة المناسب.

المبدأ الأساسي: لا توجد حالة واحدة اسمها «رقم صحيح». يجب فصل صحة الصيغة، حالة الشبكة، وجود واتساب، الاسم، السمعة، وملكية الرقم إلى أدلة مستقلة.

## التطبيقات المقترحة

| التطبيق | النقاط التي يغطيها |
|---|---|
| Phone Basics | 1–5: التنسيق، خطة الترقيم، الدولة، النوع، والشركة الأصلية |
| Network Intelligence | 4–9 و16–18: نوع الخط الحي، الشبكة الحالية، الحالة، SMS/Voice، النقل، إعادة التخصيص، وSIM Swap |
| WhatsApp Presence | 10–11: وجود حساب واتساب، مع عدم الادعاء بإثبات النشاط |
| Name & Public Identity | 12–13: الأسماء المحتملة والهوية التجارية العامة |
| Risk & Reputation | 14–18: Spam/Scam وVoIP والنقل وإعادة التخصيص وSIM Swap |
| Ownership Verification | 19: OTP أو Silent Network Authentication |
| Consent & Lifecycle | 20–21: الموافقة، المصدر، التقادم، وإعادة الفحص |
| Consensus Engine | يجمع الأدلة دون اختزالها في `valid=true/false` |

## الملفات

1. [تنسيق الرقم وتوحيده](01-format-normalization.md)
2. [صلاحية خطة الترقيم](02-numbering-plan-validity.md)
3. [الدولة والمنطقة والتوقيت](03-country-region-timezone.md)
4. [نوع الخط](04-line-type.md)
5. [شركة الاتصالات الأصلية](05-original-carrier.md)
6. [شركة الاتصالات الحالية](06-current-carrier.md)
7. [هل الخط حي وقابل للوصول؟](07-line-status-reachability.md)
8. [إمكانية استقبال SMS](08-sms-capability.md)
9. [إمكانية استقبال المكالمات](09-voice-capability.md)
10. [وجود حساب واتساب](10-whatsapp-presence.md)
11. [نشاط حساب واتساب](11-whatsapp-activity.md)
12. [الاسم المرتبط بالرقم](12-caller-name.md)
13. [هوية الشركة أو النشاط التجاري](13-business-identity.md)
14. [سمعة Spam وScam](14-spam-scam-reputation.md)
15. [VoIP والأرقام المؤقتة](15-disposable-voip-risk.md)
16. [نقل الرقم بين الشبكات](16-number-porting.md)
17. [إعادة تخصيص الرقم](17-reassigned-number.md)
18. [تغيير SIM](18-sim-swap.md)
19. [إثبات ملكية الرقم](19-ownership-verification.md)
20. [الموافقة على التواصل](20-contact-consent.md)
21. [عمر النتيجة وإعادة الفحص](21-data-freshness.md)

## الأدوات التي تجمع أكثر من نقطة

| الأداة أو الخدمة | النوع | النقاط المغطاة | الملاحظة |
|---|---|---|---|
| [Google libphonenumber](https://github.com/google/libphonenumber) | مفتوح المصدر Apache-2.0 | 1، 2، 3، 4، 5 | محلي ومجاني؛ الشركة هي الأصلية وليست الحالية |
| [libphonenumber-js](https://github.com/catamphetamine/libphonenumber-js) | مفتوح المصدر MIT | 1، 2، 3، 4 | مناسب لـJavaScript؛ يلزم `max` metadata للدقة الأعلى |
| [python-phonenumbers](https://github.com/daviddrysdale/python-phonenumbers) | مفتوح المصدر Apache-2.0 | 1، 2، 3، 4، 5 | نسخة Python من libphonenumber |
| [PhoneInfoga](https://github.com/sundowndev/PhoneInfoga) | مفتوح المصدر GPL-3.0 | 1، 2، 3، 5، 13 | OSINT ومصادر عامة؛ لا يثبت أن الخط حي أو اسم المالك |
| [HLR Lookup SDK](https://github.com/hlrlookup-com/hlrlookup-php-sdk) | SDK مفتوح + خدمة مدفوعة | 4، 6، 7، 8، 15، 16 | الكود مفتوح، أما بيانات المشغلين فمدفوعة |
| [Twilio Lookup](https://www.twilio.com/docs/lookup/v2-api) | خدمة تجارية | 1، 2، 4، 6، 7، 12، 14، 16، 17، 18 | التغطية تختلف حسب الدولة والحزمة |
| [Vonage Identity Insights](https://developer.vonage.com/de/api/number-insight?source=number-insight) | خدمة تجارية | 1، 2، 4، 6، 7، 16، 18، 19 | تجمع بيانات متعددة في API واحدة |
| [Telesign Phone ID](https://developer.telesign.com/enterprise/docs/phone-id-get-started) | خدمة تجارية | 1، 3، 4، 5، 6، 7، 8، 12، 14، 15، 16، 18 | بيانات المشترك والهوية تعتمد على التغطية والتعاقد |
| [IPQualityScore Phone Validation](https://www.ipqualityscore.com/documentation/phone-number-validation-api/overview) | خدمة تجارية | 1–7، 12، 14، 15، 20 | تجمع Validity وCarrier وActive وName وFraud وDNC |
| [CAMARA APIs](https://github.com/camaraproject) | مواصفات مفتوحة Apache-2.0 | 7، 8، 9، 16، 17، 18، 19، 20 | المواصفات مفتوحة، والتنفيذ الفعلي يحتاج مشغلًا أو مزودًا |
| [whatsmeow](https://github.com/tulir/whatsmeow) | مفتوح المصدر MPL-2.0 وغير رسمي | 10 | يفحص التسجيل على واتساب عبر جلسة Web |
| [whatsapp-web.js](https://github.com/wwebjs/whatsapp-web.js) | مفتوح المصدر Apache-2.0 وغير رسمي | 10 | يدعم `isRegisteredUser` و`getNumberId` |
| [Baileys](https://github.com/WhiskeySockets/Baileys) | مفتوح المصدر MIT وغير رسمي | 10 | إطار WhatsApp Web؛ استخدامه للفحص يحمل مخاطرة شروط الخدمة |
| [Truecaller SDK](https://docs.truecaller.com/truecaller-sdk) | خدمة مملوكة | 12، 19 | مشاركة الملف مرتبطة بموافقة صاحب الرقم، وليست قاعدة Reverse Lookup مفتوحة |
| [PhoneBlock](https://github.com/haumacher/phoneblock) | مفتوح المصدر + قاعدة مجتمعية | 14 | التغطية إقليمية ولا تصلح حكمًا منفردًا |
| [Twilio Verify](https://www.twilio.com/docs/verify/api/verification) | خدمة تجارية | 8، 9، 10، 19 | SMS وVoice وWhatsApp وSilent Network Auth |

## تصنيف الاعتماد

- **أساسي محلي:** libphonenumber أو أحد منافذه.
- **Adapter اختياري مدفوع:** HLR Lookup أو Twilio أو Vonage أو Telesign أو IPQS.
- **Pilot عالي المخاطرة:** أدوات WhatsApp Web غير الرسمية.
- **إثراء فقط:** Truecaller/Getcontact والأسماء الجماعية ومصادر OSINT.
- **دليل قوي للملكية:** OTP ناجح أو Number Verification من شبكة الهاتف.

## نموذج النتيجة الموحد

```text
raw_number
e164
possible
metadata_valid
country
region_hint
timezone_hints[]
line_type
original_carrier
current_carrier
line_status
sms_capability
voice_capability
whatsapp_status
caller_labels[]
business_matches[]
spam_risk
voip_or_disposable_risk
ported_status
reassigned_status
sim_swap_status
ownership_status
consent_status
evidence[]
checked_at
expires_at
```

## قيود عامة

- الاستخدام الشخصي لا يلغي شروط الخدمات أو قوانين الخصوصية.
- بيانات الـCrawl يجب أن تحمل مصدرًا واضحًا، ولا تتحول تلقائيًا إلى موافقة على الاتصال.
- لا يجوز تفسير فشل مزود أو Timeout على أنه رقم غير موجود.
- الاسم الجماعي ليس هوية قانونية.
- يجب عدم جمع صور واتساب أو الحالة أو البيانات الشخصية على نطاق واسع؛ واتساب يصرح بأن الجمع الآلي غير المصرح به قد يؤدي إلى الحظر. راجع [سياسة جمع المعلومات](https://faq.whatsapp.com/434518851968943).

