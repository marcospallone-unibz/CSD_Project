from flask import Flask, request
from flask_cors import CORS
import pika
from datetime import date, datetime
import requests
import uuid
import json
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

    
    def get_aggregate_by_UUID(self, uuid):
        return self.repository.get(uuid)
    
    def get_booking_by_UUID(self, uuid):
        return self.toJSON(self.repository.get(uuid))
    
    def get_booking_by_id(self, booking_id):
        booking = {}
        for b in self.bookings:
            if(str(b['booking_id']) == str(booking_id)):
                booking = b
        return self.toJSON(booking)
    
    def get_bookings(self):
        bookingsToReturn = []
        for b in self.bookings:
            bookingsToReturn.append(self.toJSON(b))
        return bookingsToReturn
        
    def insertBooking(self, itemToInsert):
        i = 1
        freeID = False
        for b in self.bookings:
            if(freeID==False):
                if(b['booking_id']!=i):
                    freeID=True
                else:
                    i += 1
        progressiveID=i
        booking = Booking(progressiveID, itemToInsert['apartmentid'], itemToInsert['fromDate'], itemToInsert['toDate'], itemToInsert['guest'])
        self.save(booking)
        send_booking_message(self.toJSON(booking))
        self.bookings.append(self.toJSON(booking))
        return booking.id
    
    def update_booking(self, itemToInsert):
        booking = self.repository.get(itemToInsert['id'])
        booking.update_booking(itemToInsert['booking_id'], itemToInsert['apartmentid'], itemToInsert['fromDate'], itemToInsert['toDate'], itemToInsert['guest'])
        self.save(booking)
        for b in self.bookings:
            if str(b['booking_id']) == str(itemToInsert['booking_id']):
                index = self.bookings.index(b)
                self.bookings[index] = itemToInsert
        return 'ok'
            
    def remove_booking(self, booking_id):
        booking = self.get_booking_by_id(booking_id)
        bookingAggregate = self.repository.get(booking['id'])
        bookingAggregate.remove_booking(bookingAggregate.booking_id)
        self.save(bookingAggregate)
        for b in self.bookings:
            if str(b['booking_id']) == str(booking_id):
                self.bookings.remove(b)
        return 'ok'
    
    def rollback_to(self, booking_id, version):
        notifications = self.get_events()
        statusToReturn = None
        n_state = None
        for n in reversed(notifications):
            n_state_json = json.loads(n.state)
            if (str(n_state_json['booking_id']) == str(booking_id) and str(n.originator_version) == str(version)):
                statusToReturn = n
                n_state = n_state_json
        if(statusToReturn!=None and n_state!=None):
            if(statusToReturn.topic == '__main__:Booking.Created' or statusToReturn.topic == '__main__:Booking.Updated'):
                bookingFounded = False
                for b in self.bookings:
                    if str(b['booking_id']) == str(booking_id):
                        bookingFounded = True
                        b['apartmentid'] = n_state['apartmentid']
                        b['fromDate'] = n_state['fromDate']
                        b['toDate'] = n_state['toDate']
                        b['guest'] = n_state['guest']
                if(not bookingFounded):
                    b = {}
                    b['id'] = uuid.uuid4()
                    b['booking_id'] = booking_id
                    b['apartmentid'] = n_state['apartmentid']
                    b['fromDate'] = n_state['fromDate']
                    b['toDate'] = n_state['toDate']
                    b['guest'] = n_state['guest']
                    self.bookings.append(b)
            elif(statusToReturn.topic == 'Booking.Removed'):
                for b in self.bookings:
                    if str(b['booking_id']) == str(booking_id):
                        self.bookings.remove(b)
            else:
                return 'NOT VALID METHOD'
        else:
            'NOTIFICATION EMPTY'
        return statusToReturn
    
    def get_events(self):
        notifications = application.notification_log.select(start=1, limit=10)
        print(notifications)
        return notifications
    
    def toJSON(self, booking):
        bookingJSON = {}
        if(isinstance(booking, Aggregate)):
            bookingJSON = {
                'id': booking.id,
                'booking_id':booking.booking_id,
                'apartmentid':booking.apartmentid,
                'fromDate':booking.fromDate,
                'toDate':booking.toDate,
                'guest':booking.guest
            }
        else:
            bookingJSON = {
                'id': booking['id'],
                'booking_id':booking['booking_id'],
                'apartmentid':booking['apartmentid'],
                'fromDate':booking['fromDate'],
                'toDate':booking['toDate'],
                'guest':booking['guest']
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
        'apartmentid':booking['apartmentid'],
        'fromDate':booking['fromDate'],
        'toDate':booking['toDate'],
        'guest':booking['guest']
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
        if(bookingToUpdate['apartmentid'] == booking['apartmentid']):
            if(date.fromisoformat(booking['fromDate']) <= fromDate <= date.fromisoformat(booking['toDate'])) or (date.fromisoformat(booking['fromDate']) <= toDate <= date.fromisoformat(booking['toDate'])) or (fromDate <= date.fromisoformat(booking['fromDate']) <= toDate) or ((fromDate <= date.fromisoformat(booking['toDate']) <= toDate)):
                print('Already booked') 
            else:
                bookingToUpdate['fromDate'] = request.args.get('fromDate')
                bookingToUpdate['toDate'] = request.args.get('toDate')
                application.update_booking(bookingToUpdate)
    return 'BOOKING UPDATED'

@app.route('/bookings/getallevents', methods=['GET'])
def get_all_events():
    application.get_events()
    return 'ok'

@app.route('/bookings/rollback', methods=['POST'])
def rollback_to():
    application.rollback_to(request.args.get('booking_id'), request.args.get('version'))
    return 'ok'
    
if __name__ == '__main__':
    os.environ["PERSISTENCE MODULE"] = "eventsourcing.sqlite"
    os.environ["SQLITE_DBNAME"] = "bookings.sqlite"
    application = BookingsService()
    app.run(host='0.0.0.0', port=8081)