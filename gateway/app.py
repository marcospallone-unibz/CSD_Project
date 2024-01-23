from flask import Flask, request
from flask_cors import CORS
import requests
from urllib.parse import urlparse
from urllib.parse import parse_qs
import json

app = Flask(__name__)

ports = {
    'apartments':8080,
    'bookings':8081,
    'search':8082,
}

@app.route('/<path:path>', methods=['GET', 'POST'])
def general_forwarding(path):
    res=None
    service = path.partition('/')[0]
    if(request.method == 'GET'):
        res = requests.get('http://'+str(service)+':'+str(ports[service])+'/'+path)
    elif(request.method == 'POST'):
        res =requests.post('http://'+str(service)+':'+str(ports[service])+'/'+path, params=parse_qs(urlparse(request.url).query))
    else:
        return 'NOT ALLOWED METHOD'
    return res.json() if res!=None else json.dumps({'Response': 'Empty response'})

if __name__=='__main__':
    app.run(host='0.0.0.0', port=8000)