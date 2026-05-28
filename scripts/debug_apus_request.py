import urllib.request
import urllib.error

url = 'http://127.0.0.1:10000/api/apus?limit=50&offset=0'
req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        print('status', resp.status)
        print(resp.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('status', e.code)
    print(e.read().decode('utf-8'))
except Exception as e:
    print('error', e)
