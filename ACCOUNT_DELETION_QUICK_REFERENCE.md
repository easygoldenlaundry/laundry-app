# Account Deletion - Quick Reference

## 🎯 For Google Play Store

### URL to Submit:
```
https://your-app-name.onrender.com/delete-account-info
```
*(Replace `your-app-name` with your actual Render.com app URL)*

### ❌ NO - These Don't Work:
- ❌ WhatsApp link - Not accepted by Google Play
- ❌ Google Docs - Not professional or permanent
- ❌ Email address only - Needs to be a web page

### ✅ YES - Use This:
- ✅ Public web page on your domain
- ✅ Explains deletion process
- ✅ Lists what data gets deleted/kept
- ✅ No login required

---

## 📱 For Your Android App

### Add Delete Button:
```kotlin
// In Settings/Account screen
Button(onClick = { deleteAccount() }) {
    Text("Delete Account")
}

fun deleteAccount() {
    // Show confirmation dialog
    // Call: DELETE /api/me/delete-account
    // Clear local data
    // Navigate to login
}
```

### API Call:
```kotlin
@DELETE("api/me/delete-account")
suspend fun deleteAccount(@Header("Authorization") token: String)
```

---

## 🌐 Endpoints Created

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/delete-account-info` | GET | Public info page | ❌ No |
| `/api/me/delete-account` | DELETE | Mobile API | ✅ Yes (Bearer token) |
| `/account/delete` | POST | Web app | ✅ Yes (Cookie) |

---

## 🗑️ What Happens When User Deletes Account

### Immediately Deleted:
- ✅ Name, email, phone, address
- ✅ Password and login credentials
- ✅ GPS coordinates
- ✅ All preferences and settings
- ✅ Complete user and customer records

### Anonymized (Kept for Legal Reasons):
- 📦 Order history (personal info removed)
- 📦 Transaction records (tax compliance)
- 📦 Financial entries (accounting)

**Retention:** Up to 10 years (German tax law)

---

## 🚀 Testing

### Test the Public Page:
```bash
curl http://localhost:8000/delete-account-info
# Should return HTML without login
```

### Test Mobile API:
```bash
# 1. Login
curl -X POST http://localhost:8000/api/auth/token/mobile \
  -H "Content-Type: application/json" \
  -d '{"username":"user@test.com","password":"pass"}'

# 2. Delete (use token from login)
curl -X DELETE http://localhost:8000/api/me/delete-account \
  -H "Authorization: Bearer <TOKEN>"
```

---

## ✅ Checklist

- [x] Public page created
- [x] Mobile API endpoint added
- [x] Web endpoint added
- [x] Data deletion implemented
- [x] Legal compliance maintained
- [x] No breaking changes
- [x] Syntax verified
- [x] Ready for production

---

## 📝 Files Changed

1. `app/templates/delete_account.html` - NEW (Public page)
2. `app/routes/users.py` - MODIFIED (Added 3 endpoints)

---

## 🎯 Next Steps

1. **Deploy to Render.com**
   ```bash
   git add .
   git commit -m "Add account deletion for Google Play compliance"
   git push
   ```

2. **Get Your URL**
   - Wait for deployment
   - Your URL: `https://YOUR-APP.onrender.com/delete-account-info`

3. **Submit to Google Play**
   - Go to Google Play Console
   - Enter your deletion URL
   - Save and submit

4. **Update Android App**
   - Add "Delete Account" button in settings
   - Call the API endpoint
   - Test thoroughly before release

---

**Done! ✅ Your app now meets Google Play data deletion requirements.**

