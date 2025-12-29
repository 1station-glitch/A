import os
import json
import random
import requests
import time
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ======================================================
# 🌍 1. إعدادات البيئة
# ======================================================
IS_GITHUB = "GITHUB_ACTIONS" in os.environ
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or "8224827964:AAGpO4HKau6MDDOHPxyBC0Lkp9hiGYCfS3M"
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID') or "5278948260"

def notify(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
        )
    except: pass

def clean_text(text):
    if not text: return ""
    return str(text).replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ة","ه").replace("ي","ى").strip()

# ======================================================
# 🔐 2. إعداد Firebase
# ======================================================
if not firebase_admin._apps:
    try:
        if IS_GITHUB:
            print("🤖 البيئة: GitHub Actions")
            firebase_config = os.environ.get("FIREBASE_JSON")
            if not firebase_config: raise ValueError("Secret Missing!")
            cred = credentials.Certificate(json.loads(firebase_config))
        else:
            print("💻 البيئة: جهاز محلي")
            local_file = "firebase_credinalt.json"
            cred = credentials.Certificate(local_file)
        
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        print(f"❌ خطأ Firebase: {e}")
        exit(1)
else:
    db = firestore.client()

# ======================================================
# 🚀 3. المحرك الرئيسي (الهادئ 🐢)
# ======================================================
def process_shipments():
    # تعديل: البحث في Shipments وعن الحالة new
    print("🔄 جاري البحث عن طلبات 'new' في 'Shipments'...")
    docs = db.collection("Shipments").where(field_path="status", op_string="==", value="new").stream()
    docs_list = list(docs)

    if not docs_list:
        print("😴 لا توجد طلبات.")
        return

    print(f"📦 جاري معالجة {len(docs_list)} طلب...")
    
    for doc in docs_list:
        try:
            order = doc.to_dict()
            doc_ref = db.collection("Shipments").document(doc.id)

            # البيانات (مفصول جاهزة)
            store_name = order.get("store_name", "")
            receiver_name = order.get("receiver_name", "")
            receiver_phone = order.get("receiver_phone", "")
            
            # نقرأ المدينة والمنطقة مباشرة
            city = order.get("city", "").strip()
            region = order.get("region", "").strip()
            
            district_street = f"{order.get('receiver_district', '')} - {order.get('receiver_street', '')}"
            

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=IS_GITHUB)
                context = browser.new_context(viewport={'width': 1280, 'height': 800})
                page = context.new_page()

                # 1️⃣ تسجيل الدخول
                print("   🔐 تسجيل الدخول...")
                page.goto("https://demo.stage.torod.co/ar/login")
                
                page.locator("input[type='email']").fill("kook53281@gmail.com")
                page.wait_for_timeout(1000) # ⏳ انتظار 1 ثانية
                
                page.locator("input[type='password']").fill("Abcd_0504989381")
                page.wait_for_timeout(1000) # ⏳ انتظار 1 ثانية
                
                # ضغط الزر بالـ XPath الخاص بك
                page.locator("xpath=/html/body/div[2]/div/div/form/p[4]/input[1]").click()
                
                page.wait_for_url("**/dashboard", timeout=60000)
                print("   ✅ تم الدخول.")

                # 2️⃣ الانتقال لصفحة الشحنة
                TARGET_URL = "https://demo.stage.torod.co/ar/shipment-create"
                page.goto(TARGET_URL)

                # 3️⃣ فتح نافذة العميل
                print("   ➕ فتح نافذة العميل...")
                page.locator("#addCustomerBtn").click()
                page.wait_for_selector("#customer_form_name", state="visible")
                page.wait_for_timeout(1000) # ⏳ انتظار بعد فتح النافذة

                # 4️⃣ تعبئة البيانات (مع تأخير)
                print("   📝 تعبئة الاسم...")
                page.locator("#customer_form_name").fill(receiver_name)
                page.wait_for_timeout(1000) # ⏳ انتظار 1 ثانية

                print("   📝 تعبئة الجوال...")
                page.locator("#customer_form_phone").fill(receiver_phone)
                page.wait_for_timeout(1000) # ⏳ انتظار 1 ثانية

                # 5️⃣ اختيار المدينة
                print(f"   🔍 اختيار المدينة: {city}")
                try:
                    CITY_BTN    = "#select2-customer_form_cities_id-container"
                    CITY_INPUT  = ".select2-search__field"
                    CITY_RESULTS= ".select2-results__options"

                    page.locator(CITY_BTN).click(force=True)
                    page.wait_for_timeout(1000) # ⏳ انتظار 1 ثانية

                    page.locator(CITY_INPUT).fill("")
                    page.locator(CITY_INPUT).type(city, delay=100) # كتابة بطيئة للأحرف
                    page.wait_for_timeout(2000) # ⏳ انتظار أطول للبحث

                    # محاولة الاختيار
                    results_list = page.locator(CITY_RESULTS).filter(has_text=city).locator("li").all()
                    if not results_list:
                         results_list = page.locator(CITY_RESULTS).locator("li").all()

                    found = False
                    target_c = clean_text(city)
                    target_r = clean_text(region)

                    if results_list:
                        for opt in results_list:
                            txt = clean_text(opt.inner_text())
                            if target_c in txt and target_r in txt:
                                opt.click()
                                found = True
                                break
                        
                        if not found:
                            for opt in results_list:
                                if target_c in clean_text(opt.inner_text()):
                                    opt.click()
                                    found = True
                                    break
                        
                        if not found: results_list[0].click()
                    
                    page.wait_for_timeout(1000) # ⏳ انتظار بعد اختيار المدينة

                except Exception as e:
                    print(f"   ⚠️ تجاوز المدينة: {e}")
                    try: page.mouse.click(0,0)
                    except: pass

                # 6️⃣ العنوان
               # 6️⃣ العنوان (الحل النهائي لمشكلة عدم الكتابة)
                print("   🗺️ معالجة العنوان...")
                
                # 1. إغلاق الخريطة إجبارياً
                # نتأكد إذا الزر موجود ومفعل، نطفيه
                map_toggle = page.locator("#customer_form_google_map_toggle")
                if map_toggle.is_visible() and map_toggle.is_checked():
                     print("   🚫 إغلاق زر الخريطة للسماح بالكتابة...")
                     map_toggle.click(force=True)
                     page.wait_for_timeout(1500) # ننتظر شوي لين يفتح خانة الكتابة

                # 2. الكتابة في الخانة
                address_box = page.locator("#customer_form_address_details")
                
                # نضغط داخل الصندوق أولاً (عشان الموقع يحس)
                address_box.click(force=True)
                
                # نكتب البيانات
                if district_street:
                    print(f"   ✍️ كتابة: {district_street}")
                    address_box.fill(district_street)
                else:
                    print("   ⚠️ تنبيه: العنوان (الحي والشارع) فارغ!")
                    address_box.fill("city_region")

                page.wait_for_timeout(1000) # استراحة

                notify(f"🐢 <b>عنوان استلام جديد</b>\n👤 {receiver_name}\n📍 {city}\n🚨 اسم المستلم {store_name}\n📱 الرقم: {receiver_phone}\n📍 المدينة - المنطقة: {city} - {region}\n🏘️ الحي - الشارع: {district_street}")
                # 7️⃣ الحفظ
                SAVE_BTN = "#add_customer_form_btn"
                print("   💾 جاري الحفظ...")
                page.locator(SAVE_BTN).click()

                # التحقق
                try:
                    page.wait_for_selector("#customer_form_name", state="hidden", timeout=30000)
                    
                    # النجاح
                    doc_ref.update({"status": "customer_added"}) 
                    notify(f"✅ <b>تم إضافة العميل ببطء ورواق:</b>\n{receiver_name}")
                    
                    # 👇 الجملة اللي طلبتها
                    print("تم الاضافة")

                except:
                    notify(f"❌ فشل الحفظ\n{receiver_name}")
                    print("فشل الاضافة")

                browser.close()

        except Exception as e:
            print(f"❌ خطأ: {e}")
            notify(f"⚠️ خطأ: {e}")

if __name__ == "__main__":
    process_shipments()
