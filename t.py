import requests
import json

url = 'https://kauth.kakao.com/oauth/token'
client_id = '자신의 REST_API키를 입력하세요'
redirect_uri = 'https://example.com/oauth'
code = '자신의 CODE입력'

data = {
    'grant_type':'authorization_code',
    'client_id':client_id,
    'redirect_uri':redirect_uri,
    'code': code,
    }

response = requests.post(url, data=data)
tokens = response.json()

#발행된 토큰 저장
with open("kakaotalk.json","w") as kakao:
    json.dump(tokens, kakao)