# Facebook Marketing API Setup

## 1. Create Facebook App
- Go to https://developers.facebook.com/
- Create new app → Business → Skip → Enter app name
- Add "Marketing API" product to your app

## 2. Get API Credentials
- **App ID**: Found in app settings
- **App Secret**: Found in app settings → Basic
- **Access Token**: Tools → Graph API Explorer → Get User Access Token
  - Select permissions: `ads_management`, `business_management`, `ads_read`

## 3. Get Ad Account ID
- Go to Facebook Business Manager: https://business.facebook.com/
- Settings → Accounts → Ad Accounts → Copy ID (format: `act_123456789`)

## 4. Set Environment Variables
Add to your `.env` file:

FACEBOOK_ACCESS_TOKEN=your_token
FACEBOOK_APP_SECRET=your_secret
FACEBOOK_APP_ID=your_app_id
FACEBOOK_AD_ACCOUNT_ID=act_your_account_id

## 5. Test Configuration
The system will validate your credentials on startup.