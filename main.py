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
# 🚀 3. المحرك الرئيسي (إضافة عميل جديد)
# ======================================================
def process_shipments():
    print("🔄 جلب الطلبات (pending)...")
    docs = db.collection("orders").where("status", "==", "pending").stream()
    docs_list = list(docs)

    if not docs_list:
        print("😴 لا توجد طلبات.")
        return

    print(f"📦 جاري معالجة {len(docs_list)} طلب...")
    
    for doc in docs_list:
        try:
            order = doc.to_dict()
            doc_ref = db.collection("orders").document(doc.id)

            # استخراج البيانات
            store_name = order.get("store_name", "")
            receiver_name = order.get("receiver_name", "")
            receiver_phone = order.get("receiver_phone", "")
            city = order.get("city", "")
            region = order.get("region", "")
            district_street = f"{order.get('district', '')} - {order.get('street', '')}"
            
            notify(f"🚀 <b>بدء إضافة عميل:</b>\n👤 {receiver_name}\n📍 {city}")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=IS_GITHUB)
                context = browser.new_context(viewport={'width': 1280, 'height': 800})
                page = context.new_page()

                # 1️⃣ تسجيل الدخول
                page.goto("https://demo.stage.torod.co/ar/login")
                page.locator("input[type='email']").fill("kook53281@gmail.com")
                page.locator("input[type='password']").fill("Abcd_0504989381")
                page.locator("button[type='submit']").click()
                page.wait_for_url("**/dashboard", timeout=60000)

                # 2️⃣ الانتقال لصفحة إنشاء شحنة
                TARGET_URL = "https://demo.stage.torod.co/ar/shipment-create"
                print(f"   🔗 الانتقال إلى: {TARGET_URL}")
                page.goto(TARGET_URL)

                # 3️⃣ فتح نافذة إضافة عميل
                print("   ➕ فتح نافذة 'عميل جديد'...")
                page.locator("#addCustomerBtn").click()
                
                # انتظار ظهور النافذة
                page.wait_for_selector("#customer_form_name", state="visible")

                # 4️⃣ تعبئة الاسم والجوال
                print("   📝 تعبئة البيانات الشخصية...")
                page.locator("#customer_form_name").fill(receiver_name)
                page.locator("#customer_form_phone").fill(receiver_phone)

                # ---------------------------------------------------------
                # 🏙️ 5️⃣ اختيار المدينة (بالمعرفات الجديدة)
                # ---------------------------------------------------------
                # المعرفات التي أرسلتها:
                CITY_BTN    = "#select2-customer_form_cities_id-container"
                CITY_INPUT  = ".select2-search__field"     # حذفنا valid لأنها متغيرة
                CITY_RESULTS= ".select2-results__options"  # الكلاس الخاص بالقائمة

                print(f"   🔍 اختيار المدينة: {city}")
                try:
                    # فتح القائمة
                    page.locator(CITY_BTN).click(force=True)
                    
                    # الكتابة
                    page.locator(CITY_INPUT).fill("")
                    page.locator(CITY_INPUT).type(city, delay=100)
                    
                    # الانتظار
                    page.wait_for_timeout(4000)

                    # البحث في النتائج
                    # بما أن المحدد هو كلاس، نستخدم first أو نتأكد أنه المرئي
                    results_list = page.locator(CITY_RESULTS).filter(has_text=city).locator("li").all()
                    
                    # إذا الفلتر السابق ما جاب نتيجة، نجيب كل الخيارات المرئية
                    if not results_list:
                         results_list = page.locator(CITY_RESULTS).locator("li").all()

                    found = False
                    target_c = clean_text(city)
                    target_r = clean_text(region)

                    if results_list:
                        for opt in results_list:
                            txt = clean_text(opt.inner_text())
                            # تطابق: المدينة + المنطقة
                            if target_c in txt and target_r in txt:
                                print(f"      ✅ تطابق كامل: {opt.inner_text()}")
                                opt.click()
                                found = True
                                break
                        
                        # محاولة ثانية: المدينة فقط
                        if not found:
                            for opt in results_list:
                                if target_c in clean_text(opt.inner_text()):
                                    print(f"      ⚠️ تطابق مدينة فقط: {opt.inner_text()}")
                                    opt.click()
                                    found = True
                                    break
                        
                        # محاولة أخيرة: أول خيار
                        if not found: 
                             print("      🎲 اختيار عشوائي (أول نتيجة).")
                             results_list[0].click()
                    else:
                        print("      ⚠️ القائمة فارغة!")

                except Exception as e:
                    print(f"   ❌ خطأ في المدينة: {e}")
                    try: page.mouse.click(0,0)
                    except: pass

                # 6️⃣ العنوان والخريطة
                print("   🗺️ إعداد العنوان...")
                if page.locator("#customer_form_google_map_toggle").is_checked():
                     page.locator("#customer_form_google_map_toggle").click(force=True)
                
                page.locator("#customer_form_address_details").fill(district_street)

                # ---------------------------------------------------------
                # 🏁 7️⃣ الحفظ (بالزر الجديد)
                # ---------------------------------------------------------
                SAVE_BTN = "#add_customer_form_btn"
                print(f"   💾 الضغط على زر الحفظ ({SAVE_BTN})...")
                
                page.locator(SAVE_BTN).click()

                # التحقق من النجاح (اختفاء النافذة)
                try:
                    # ننتظر اختفاء النافذة لمدة 30 ثانية
                    page.wait_for_selector("#customer_form_name", state="hidden", timeout=30000)
                    
                    # ✅ نجاح
                    doc_ref.update({"status": "customer_added"}) 
                    notify(f"✅ <b>تمت إضافة العميل:</b>\n{receiver_name}")
                    print("   ✅ تم بنجاح.")

                except:
                    # ❌ فشل (النافذة ما زالت موجودة)
                    notify(f"❌ فشل إضافة العميل (رفض الموقع)\n{receiver_name}")
                    print("   ❌ فشل (النافذة معلقة).")

                browser.close()

        except Exception as e:
            print(f"❌ خطأ عام: {e}")
            notify(f"⚠️ خطأ: {e}")

if __name__ == "__main__":
    process_shipments()
