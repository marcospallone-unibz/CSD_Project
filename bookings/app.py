from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import pika
from datetime import date
import requests

from eventsourcing.domain import Aggregate, event
from eventsourcing.application import Application
import os

app = Flask(__name__)

apartmentsIDs = []

class Booking(Aggregate):
    @event('Created')
    def __init__(self, booking_id, apartmentid, fromDate, toDate, guest):
        self.booking_id = booking_id
        self.apartmentid = apartmentid
        self.fromDate = fromDate
        self.toDate = toDate
        self.guest = guest
        
    @event('Updated')
    def update_booking(self, booking_id, apartmentid, fromDate, toDate, guest):
        self.booking_id = booking_id
        self.apartmentid = apartmentid
        self.fromDate = fromDate
        self.toDate = toDate
        self.guest = guest
        
    @event('Removed')
    def remove_booking(self, booking_id):
        self.booking_id = booking_id
        self.apartmentid = None
        self.fromDate = None
        self.toDate = None
        self.guest = None
        
class BookingsService(Application):
    progressiveID = 0
    bookings = []
    
    def get_booking_by_UUID(self, uuid):
        return self.toJSON(self.repository.get(uuid))
    
    def get_booking_by_id(self, booking_id):
        booking = {}
        for b in self.bookings:
            if(str(b.booking_id) == str(booking_id)):
                booking = self.repository.get(b.id)
        return self.toJSON(booking)
    
    def get_bookings(self):
        return self.bookings
        
    def insertBooking(self, itemToInsert):
        i = 1
        freeID = False
        for b in self.bookings:
            if(freeID==False):
                if(b.booking_id!=i):
                    freeID=True
                else:
                    i += 1
        progressiveID=i
        print('PROGRESSIVEID', progressiveID)
        booking = Booking(progressiveID, itemToInsert['apartmentid'], itemToInsert['fromDate'], itemToInsert['toDate'], itemToInsert['guest'])
        self.save(booking)
        send_booking_message(booking)
        self.bookings.append(booking)
        return booking.id
    
    def update_booking(self, itemToInsert):
        if(isinstance(itemToInsert, Booking)):
            itemToInsert.update_booking(itemToInsert['booking_id'], itemToInsert['apartmentid'], itemToInsert['fromDate'], itemToInsert['toDate'], itemToInsert['guest'])
        if(itemToInsert not in self.bookings):
            self.bookings.append(itemToInsert['id'])
        return 'ok'
            
    def remove_booking(self, booking_id):
        Booking.remove_booking(booking_id)
        if(booking_id in self.bookingsIDs):
            self.bookingsIDs.remove(booking_id)
        return 'ok'
    
    '''def get_events(self):
        notifications = application.notification_log.select(start=1, limit=10)
        print(notifications)'''
    
    def toJSON(self, booking):
        bookingJSON = {
            'apartmentid':booking.apartmentid,
            'fromDate':booking.fromDate,
            'toDate':booking.toDate,
            'guest':booking.guest
        }
        return bookingJSON

def listening():
    credentials = pika.PlainCredentials('guest', 'guest')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', 5672, '/', credentials))
    channel = connection.channel()
    channel.queue_declare(queue='A-B')
    def callback(ch, method, properties, body):
        if(properties.headers['action']=='add'):
            if(properties.headers['id'] not in apartmentsIDs):
                apartmentsIDs.append(properties.headers['id'])
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
    bookingProperty = {
        'apartmentid':booking.apartmentid,
        'fromDate':booking.fromDate,
        'toDate':booking.toDate,
        'guest':booking.guest
    }
    properties = pika.BasicProperties(headers={'booking':bookingProperty, 'from':'bookings'})
    channel.basic_publish(exchange='addbooking', routing_key='', body='Change in bookings!', properties=properties)
    connection.close()

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
    listening()

@app.route('/bookings/list', methods=['GET'])
def api_get_bookings():
    bookings = application.get_bookings()
    print(bookings)
    return 'ok'

@app.route('/bookings/add', methods=['POST'])
def api_add_booking():
    if(request.args.get('apartmentid') in apartmentsIDs):
        booked = False
        fromDate = date.fromisoformat(request.args.get('fromDate'))
        toDate = date.fromisoformat(request.args.get('toDate'))
        for booking in application.get_bookings():
            print('BOOKING', booking)
            if(booking['apartmentid']==request.args.get('apartmentid')):
                if(date.fromisoformat(booking['fromDate']) <= fromDate <= date.fromisoformat(booking['toDate'])) or (date.fromisoformat(booking['fromDate']) <= toDate <= date.fromisoformat(booking['toDate'])) or (fromDate <= date.fromisoformat(booking['fromDate']) <= toDate) or ((fromDate <= date.fromisoformat(booking['toDate']) <= toDate)):
                    booked = True                
        if(booked==True):
            return 'Already Booked'
        else:
            itemToInsert = {
                    'apartmentid': request.args.get('apartmentid'),
                    'fromDate': request.args.get('fromDate'),
                    'toDate': request.args.get('toDate'),
                    'guest': request.args.get('guest')
            }
            application.insertBooking(itemToInsert)
    else:
        return 'Apartment not exists'
    return 'BOOKING INSERTED'

@app.route('/bookings/cancel', methods=['POST'])
def api_remove_booking():
    application.remove_booking(request.args.get('id'))
    return 'BOOKING DELETED'

@app.route('/bookings/change', methods=['POST'])
def api_update_booking():
    fromDate = date.fromisoformat(request.args.get('fromDate'))
    toDate = date.fromisoformat(request.args.get('toDate'))
    bookingToUpdate = application.get_booking_by_id(request.args.get('id'))
    print('TOUPDATE198', bookingToUpdate)
    for booking in application.get_bookings():
        print('BOOKING200', booking)
        if(bookingToUpdate.apartmentid == booking.apartmentid):
            if(date.fromisoformat(booking['fromDate']) <= fromDate <= date.fromisoformat(booking['toDate'])) or (date.fromisoformat(booking['fromDate']) <= toDate <= date.fromisoformat(booking['toDate'])) or (fromDate <= date.fromisoformat(booking['fromDate']) <= toDate) or ((fromDate <= date.fromisoformat(booking['toDate']) <= toDate)):
                print('Already booked') 
            else:
                bookingToUpdate['fromDate'] = request.args.get('fromDate')
                bookingToUpdate['toDate'] = request.args.get('toDate')
                application.update_booking(bookingToUpdate)
    return 'BOOKING UPDATED'
    
if __name__ == '__main__':
    os.environ["PERSISTENCE MODULE"] = "eventsourcing.sqlite"
    os.environ["SQLITE_DBNAME"] = "bookings.sqlite"
    application = BookingsService()
    app.run(host='0.0.0.0', port=8081)