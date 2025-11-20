import os
from dotenv import load_dotenv

load_dotenv()

ADDS_URL = 'https://api.direct.yandex.com/json/v5/ads'
COPMPAIGNS_URL = 'https://api.direct.yandex.com/json/v5/campaigns'
ADDS_GROUP = 'https://api.direct.yandex.com/json/v5/adgroups'
FAST_LINKS = 'https://api.direct.yandex.com/json/v5/sitelinks'


CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

REDIRECT_URL = 'https://oauth.yandex.ru/verification_code'
USER_INFO_URL = 'https://login.yandex.ru/info'
AUTH_URL = 'https://oauth.yandex.ru/authorize'
TOKEN_URL = 'https://oauth.yandex.ru/token'

GET_COM_JSON = {
    "method": "get",
    "params": {
        "SelectionCriteria": {},
        "FieldNames": ["Id", "Name", "State"]
    }
}
