
import smtplib

# ⚠️ Yahan dhyan se type karein
EMAIL = "thakurdps795@gmail.com"  # Spelling check karein!
PASSWORD = "micf yhhh ckmn gvwh"  # Bina space ke

try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    print(f"Checking credentials for {EMAIL}...")
    server.login(EMAIL, PASSWORD)
    print("✅ SUCCESS! Password sahi hai. Ab app.py chalega.")
    server.quit()
except Exception as e:
    print(f"❌ ERROR: {e}")