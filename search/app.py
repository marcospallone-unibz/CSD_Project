from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import pika
from datetime import date, time, datetime
import copy
import requests

app = Flask(__name__)

allApartments = []
bookings = []
availableApartments = []

def listening():
    credentials = pika.PlainCredentials('guest', 'guest')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', 5672, '/', credentials))
    channel = connection.channel()

    channel.queue_declare(queue='A-S')
    channel.queue_declare(queue='B-S')

    def callback(ch, method, properties, body):
        if(properties.headers['from'] == 'apartments'):
            if(properties.headers['action'] == 'add'):
                if(properties.headers['id'] not in allApartments):
                    allApartments.append(properties.headers['id'])
            elif(properties.headers['action'] == 'remove'):
                allApartments.remove(properties.headers['id'])
            print(allApartments)
        elif(properties.headers['from'] == 'bookings'):
            booking = properties.headers['booking']
            exist = False
            if(booking != None):
                for b in bookings:
                    if(booking['id'] == b['id']):
                        exist = True
                        b = booking
                if(exist == False):
                    bookings.append(booking)
            print(bookings)
            print(allApartments)

    channel.basic_consume(queue='A-S', on_message_callback=callback, auto_ack=True)
    channel.basic_consume(queue='B-S', on_message_callback=callback, auto_ack=True)

    print(' [*] Waiting for messages')
    channel.start_consuming()

def connect_to_db():
    conn = sqlite3.connect('database.db')
    return conn

def create_db_table():
    try:
        conn = connect_to_db()
        conn.execute('''
            CREATE TABLE apartmentsList (
                id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                size INTEGER NOT NULL
            );
        ''')
        conn.execute('''
            CREATE TABLE bookingsList (
                id INTEGER PRIMARY KEY NOT NULL,
                apartmentid INTEGER NOT NULL,
                fromDate TEXT NOT NULL,
                toDate TEXT NOT NULL,
                guest TEXT NOT NULL
            );
        ''')
        conn.commit()
        print("tables created successfully")
    except:
        print("tables creation failed")
    finally:
        conn.close()

def checkIfTableExist():
        conn = connect_to_db()
        cur = conn.cursor()
        listOfTables = cur.execute(
            """SELECT name FROM sqlite_master WHERE type='table'
            AND name='apartmentsList'; """).fetchall()
        listOfTables.append(cur.execute(
            """SELECT name FROM sqlite_master WHERE type='table'
            AND name='bookingsList'; """).fetchall())
        if listOfTables == []:
            return False
        else:
            return True
        
def findAvailableApartments(fromDate, toDate):
        print(allApartments)
        availableApartments = copy.deepcopy(allApartments)
        for b in bookings:
            if(date.fromisoformat(b['fromDate']) <= fromDate <= date.fromisoformat(b['toDate'])) or (date.fromisoformat(b['fromDate']) <= toDate <= date.fromisoformat(b['toDate'])) or (fromDate <= date.fromisoformat(b['fromDate']) <= toDate) or ((fromDate <= date.fromisoformat(b['toDate']) <= toDate)):
                if(str(b['apartmentid']) in availableApartments):
                    availableApartments.remove(str(b['apartmentid']))
        print(availableApartments)

def directCall_toApartments():
    allApartments = []
    res = requests.get('http://apartments:8080/apartments/list')
    for a in res.json():
        allApartments.append(a['id'])
    print(allApartments)

def directCall_toBookings():
    bookings = []
    res = requests.get('http://bookings:8081/bookings/list')
    for b in res.json():
        bookings.append(b)
    print(bookings)

@app.route('/search/callapartments', methods=['GET'])
def call_apartments():
    directCall_toApartments()
    return 'Apartments directly called'

@app.route('/search/callbookings', methods=['GET'])
def call_bookings():
    directCall_toBookings()
    return 'Bookings directly called'
        
@app.route('/search/register', methods=['GET'])
def start_rabbit():
    if checkIfTableExist()==False:
        create_db_table()
    listening()

@app.route('/search/search', methods=['GET'])
def api_get_search():
    findAvailableApartments(date.fromisoformat(request.args.get('from')), date.fromisoformat(request.args.get('to')))
    return(jsonify(availableApartments))

if __name__=='__main__':
    app.run(host='0.0.0.0', port=8082)