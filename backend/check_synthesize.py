import json
import urllib.request
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/synthesize',
    data=b'{"query": "group by region and calculate total revenue per region", "task_type": "data_analysis"}',
    headers={'Content-Type': 'application/json'}
)
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except Exception as e:
    print(e)
