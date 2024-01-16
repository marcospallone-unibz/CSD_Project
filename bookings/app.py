from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import pika
from datetime import date, time, datetime
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

app = Flask(__name__)

apartmentsIDs = []
addedID = None

def listening():

    credentials = pika.PlainCredentials('guest', 'guest')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', 5672, '/', credentials))
    channel = connection.channel()

    channel.queue_declare(queue='A-B')

    def callback(ch, method, properties, body):
        global addedID
        if(properties.headers['action']=='add'):
            if(properties.headers['id'] not in apartmentsIDs):
                addedID=properties.headers['id']
                apartmentsIDs.append(addedID)
        elif(properties.headers['action']=='remove'):
            apartmentsIDs.remove(properties.headers['id'])
        print(apartmentsIDs)

    channel.basic_consume(queue='A-B', on_message_callback=callback, auto_ack=True)

    print(' [*] Waiting for messages')
    channel.start_consuming()

def send_booking_message(booking):
    credentials = pika.PlainCredentials('guest', 'guest')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', 5672, '/', credentials))

    channel = connection.channel()

    channel.exchange_declare('addbooking', 'fanout')

    channel.queue_declare(queue='B-S')

    channel.queue_bind('B-S', 'addbooking')

    properties = pika.BasicProperties(headers={'booking':booking, 'from':'bookings'})
  
    channel.basic_publish(exchange='addbooking', routing_key='', body='Change in bookings!', properties=properties)
   
    connection.close()


def connect_to_db():
    conn = sqlite3.connect('database.db')
    return conn

def create_db_table():
    try:
        conn = connect_to_db()
        conn.execute('''
            CREATE TABLE bookings (
                id INTEGER PRIMARY KEY NOT NULL,
                apartmentid INTEGER NOT NULL,
                fromDate TEXT NOT NULL,
                toDate TEXT NOT NULL,
                guest TEXT NOT NULL
            );
        ''')
        conn.commit()
        print("bookings table creation successful")
    except:
        print("bookings table creation failed")
    finally:
        conn.close()

def checkIfTableExist():
        conn = connect_to_db()
        cur = conn.cursor()
        listOfTables = cur.execute(
            """SELECT name FROM sqlite_master WHERE type='table'
            AND name='bookings'; """).fetchall()
        if listOfTables == []:
            return False
        else:
            return True

def insertBooking(itemToInsert):
    inserted = {}
    try:
        conn = connect_to_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO bookings (apartmentid, fromDate, toDate, guest) VALUES (?, ?, ?, ?)",
                     (itemToInsert['apartmentid'], itemToInsert['fromDate'], itemToInsert['toDate'], itemToInsert['guest']))
        conn.commit()
        print('bookings97')
        print(cur.lastrowid)
        inserted = get_booking_by_id(cur.lastrowid)
        print('bookings100')
        print(inserted)
        send_booking_message(inserted)
    except:
        conn.rollback()
    finally:
        conn.close()
    return inserted

def get_bookings():
    bookings = []
    try:
        conn = connect_to_db()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM bookings")
        rows = cur.fetchall()
        # convert row objects to dictionary
        for i in rows:
            booking = {}
            booking["id"] = i["id"]
            booking["apartmentid"] = i["apartmentid"]
            booking["fromDate"] = i["fromDate"]
            booking["toDate"] = i["toDate"]
            booking["guest"] = i["guest"]
            bookings.append(booking)
    except:
        bookings = []
    return bookings

def get_booking_by_id(id):
    booking = {}
    try:
        conn = connect_to_db()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM bookings WHERE id = ?", (str(id)))
        row = cur.fetchone()
        # convert row object to dictionary
        booking["id"] = row["id"]
        booking["apartmentid"] = row["apartmentid"]
        booking["fromDate"] = row["fromDate"]
        booking["toDate"] = row["toDate"]
        booking["guest"] = row["guest"]
    except Exception as e: 
        print(e)
        booking = {}
    return booking

def update_booking(booking):
    updated_booking = {}
    try:
        conn = connect_to_db()
        cur = conn.cursor()
        cur.execute("UPDATE bookings SET fromDate = ?, toDate = ? WHERE id = ?",  
                     (booking['fromDate'], booking['toDate'], booking['id']))
        conn.commit()
        updated_booking = get_booking_by_id(booking["id"])
        send_booking_message(updated_booking)
    except:
        conn.rollback()
        updated_booking = {}
    finally:
        conn.close()
    return updated_booking

def delete_booking(id):
    try:
        conn = connect_to_db()
        conn.execute("DELETE from bookings WHERE id = ?",(id))
        conn.commit()
    except:
        conn.rollback()
    finally:
        conn.close()

def directCall_toApartments():
    apartmentsIDs = []
    res = requests.get('http://apartments:8080/apartments/list')
    for a in res.json():
        apartmentsIDs.append(a['id'])
    print(apartmentsIDs)

@app.route('/bookings/callapartments', methods=['GET'])
def call_apartments():
    directCall_toApartments()
    return 'Apartments directly called'

@app.route('/bookings/start', methods=['GET'])
def start_rabbit():
    if checkIfTableExist()==False:
        create_db_table()
    listening()

@app.route('/bookings/list', methods=['GET'])
def api_get_bookings():
    return jsonify(get_bookings())

@app.route('/bookings/add', methods=['POST'])
def api_add_booking():
    if(request.args.get('apartmentid') in apartmentsIDs):
        itemToInsert = {
            'apartmentid': request.args.get('apartmentid'),
            'fromDate': request.args.get('fromDate'),
            'toDate': request.args.get('toDate'),
            'guest': request.args.get('guest')
        }
        insertBooking(itemToInsert)
    else:
        print('Apartment not exists')
    return jsonify(get_bookings())

@app.route('/bookings/cancel', methods=['POST'])
def api_remove_booking():
    delete_booking(request.args.get('id'))
    return jsonify(get_bookings())

@app.route('/bookings/change', methods=['POST'])
def api_update_booking():
    fromDate = date.fromisoformat(request.args.get('fromDate'))
    toDate = date.fromisoformat(request.args.get('toDate'))
    bookingToUpdate = get_booking_by_id(request.args.get('id'))
    bookings = get_bookings()
    for booking in bookings:
        if(bookingToUpdate['apartmentid'] == booking['apartmentid']):
            if(date.fromisoformat(booking['fromDate']) <= fromDate <= date.fromisoformat(booking['toDate'])) or (date.fromisoformat(booking['fromDate']) <= toDate <= date.fromisoformat(booking['toDate'])) or (fromDate <= date.fromisoformat(booking['fromDate']) <= toDate) or ((fromDate <= date.fromisoformat(booking['toDate']) <= toDate)):
                print('Already booked') 
            else:
                bookingToUpdate['fromDate'] = request.args.get('fromDate')
                bookingToUpdate['toDate'] = request.args.get('toDate')
                print(bookingToUpdate)
                update_booking(bookingToUpdate)
    return jsonify(get_bookings())

if __name__ == '__main__':
    retry_strategy = Retry( total=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry_strategy)
    http = requests.Session()
    http.mount("https://", adapter)
    http.mount("http://", adapter)
    app.run(host='0.0.0.0', port=8081)