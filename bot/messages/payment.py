SUBSCRIPTION_MESSAGE = """
👻 Choose payment method: ⚡️ Pay-as-You-Go System ⚡️

💎 <b>Crypto:</b>
  ↵ Pay using your Web3 wallet for secure blockchain-based transactions
  
🇱🇾 <b>Libyan Payments:</b>
  ↵ Pay in Libyan currency, ideal for local users
  
💳 <b>Visa/Master:</b>
  ↵ Convenient for worldwide users, accepted globally

💰 <b>Anis USDT:</b>
  ↵ The easiest and most straightforward payment method
  
🏴‍☠️<b>GX Cards:</b>
  ↵ Exciting new option coming soon!
  
❤️‍🩹<b>Donation</b>
  ↵ Your support helps us keep going. Every contribution matters!
"""

SUBSCRIPTION_MESSAGE_AR = """
👻 جميع الخطط ستمنحك:⚡️ نظام الدفع حسب الاستخدام ⚡️

💎 <b>العملات الرقمية:</b>
  ↵ ادفع باستخدام محفظك المشفرة الخاصة بك لإجراء معاملات آمنة مبنية على البلوك تشين
  
🇱🇾 <b>طرق الدفع الليبية:</b>
  ↵ ادفع بالعملة الليبية، مثالية للمستخدمين المحليين
  
💳 <b>فيزا/ماستركارد:</b>
  ↵ مريحة للمستخدمين حول العالم، مقبولة عالميًا

💰 <b>أنيس USDT:</b>
  ↵ أسهل وأبسط طريقة للدفع
  
🏴‍☠️ <b>بطاقات GX:</b>
  ↵ قادم قريبًا
  
❤️‍🩹 <b>التبرعات:</b>
  ↵  دعمكم يساعدنا على الاستمرار. كل مساهمة تهم

"""

PAYMENT_MESSAGE = """
🔐 We use a trusted payment service Cryptomus. We do not store your payment data. Once you make a payment, you will receive a confirmation message.
"""

PAYMENT_MESSAGE_AR = """
🔐 نحن نستخدم خدمة الدفع الموثوقة Cryptomus. لا نقوم بتخزين بيانات الدفع الخاصة بك. بمجرد قيامك بعملية الدفع، ستتلقى رسالة تأكيد.
"""

PAYMENT_LINK = "Hit the following link to start the payment process"
PAYMENT_LINK_AR = "انقر على الرابط التالي لبدء عملية الدفع"

SEND_REDEEM = "Please to start adding your redeem card click here /redeem"
SEND_REDEEM_AR = (
    "يرجى البدء بإضافة الرمز السري المكون من حروف وارقام، انقر هنا /redeem."
)

REDEEM_ME = "Send me your <b>redeem card code</b>"
REDEEM_ME_AR = "ابعث لي الرمز السري"


def get_payment_message(payment_choice):
    payment_message = {
        "crypto": "The link below leads you to the process of paying us directly using cryptocurrencies\n\n"
        "🚨<b>NOTE</b>: That the payment is made directly from your electronic wallet to our wallet, "
        "and the transaction is carried out through the Binance platform, which provides the highest levels of security\n",
        "libyan-payments": "The link below leads you to the process of paying us in Libyan currency through "
        "various methods (bank card - Pay for me - Mobi Cash - Sadad - Tadawul)\n\n"
        "🚨<b>NOTE</b>: We apply the highest levels of security and adhere in our transactions "
        "to all the security policies imposed by the Central Bank of Libya\n",
        "visa-master": "coming soon",
        "anis-usdt": "Send me your redeem card code so i can add it to your balance\n\n"
        "🚨<b>NOTE</b>: we will check the code first before we add, please write and send the code alone without any extra word\n",
        "gx-cards": "Coming Soon",
        "donation": "Coming Soon",
    }

    return payment_message.get(payment_choice, None)


def get_payment_message_ar(payment_choice):
    payment_message = {
        "crypto": "الرجاء اختيار القيمة في الاسفل 💸\n\n"
        "🚨<b>تنويه</b>:  تنويه عملية الدفع تتم من محفظتك الالكترونية مباشرة الى محفظتنا"
        " والمعاملة تتم بواسطة منصة بايننس التي توفر أعلى مستويات الأمان",
        "libyan-payments": "الرجاء اختيار القيمة في الاسفل 💸"
        " عبر عدة طرق ( البطاقة المصرفية - إدفع لي - موبي كاش - سداد - تداول )\n\n"
        "🚨<b>تنويه</b>: نطبق أعلى مستويات الأمان و نخضع في تعاملاتنا لكافة سياسات الأمان التي يفرضها مصرف ليبيا المركزي\n",
        "visa-master": "قريبا",
        "anis-usdt": "ابعث لي الرمز السري الموجود في كرت انيس حتى اتمكن من اضافتها لرصيدك\n\n"
        "🚨<b>تنويه</b>: يرجى كتابة الرمز وإرساله فقط دون أي كلمات إضافية\n",
        "gx-cards": "قريبا",
        "donation": "قريبا",
    }

    return payment_message.get(payment_choice, None)


BALANCE_IS_ZERO_AR = """
رصيد غير كاف. أنت بحاجة على الأقل إلى <b>{}</b> للمتابعة.
"""

BALANCE_IS_ZERO = """
Insufficient balance. You need at least {} credits to continue.
"""

ADD_BALANCE = """
🌟 Attention {},
It seems your balance has reached zero. To continue enjoying our exclusive features, a top-up is needed.
🚀 Quick Tip: Recharging now ensures uninterrupted access to all the amazing services we offer. Plus, you might discover some new,
exciting features too!
💳 Recharge Now: /payment
We're here to assist if you need any help. Thank you for using GX GPT!
"""

ADD_BALANCE_AR = """
🌟 مرحبا {},
يبدو أن رصيدك قد وصل إلى الانتهاء. لمواصلة الاستمتاع بميزاتنا الحصرية، يمكنك إعادة تعبئة الرصيد.
🚀 نصيحة سريعة: إعادة الشحن الآن تضمن الوصول دون انقطاع إلى جميع الخدمات الرائعة التي نقدمها. بالإضافة إلى ذلك، قد تكتشف بعض الميزات الجديدة،
ميزات مثيرة أيضًا!
💳 أعد الشحن الآن:payment/
نحن هنا لمساعدتك إذا كنت بحاجة إلى أي مساعدة. شكرًا لك على استخدام GX GPT!
"""
