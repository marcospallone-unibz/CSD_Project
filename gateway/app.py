from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from urllib.parse import urlparse
from urllib.parse import parse_qs
import docker

app = Flask(__name__)

ports = {
    'apartments':8080,
    'bookings':8081,
    'search':8082,
}

@app.route('/<path:path>', methods=['GET', 'POST'])
def general_forwarding(path):
    service = path.partition('/')[0]
    if(request.method == 'GET'):
        requests.get('http://localhost:'+str(ports[service])+'/'+path)
    elif(request.method == 'POST'):
        requests.post('http://localhost:'+str(ports[service])+'/'+path, params=parse_qs(urlparse(request.url).query))
    else:
        return 'NOT ALLOWED METHOD'
    return 'Request Forwarded'

if __name__=='__main__':
    app.run(host='0.0.0.0', port=8000)