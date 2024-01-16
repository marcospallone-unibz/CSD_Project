from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import pika

app = Flask(__name__)

def connect_rabbit(insertedItem, action):
    credentials = pika.PlainCredentials('guest', 'guest')
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', 5672, '/', credentials))

    channel = connection.channel()

    channel.exchange_declare('addapartment', 'fanout')

    channel.queue_declare(queue='A-B')
    channel.queue_declare(queue='A-S')

    channel.queue_bind('A-B', 'addapartment')
    channel.queue_bind('A-S', 'addapartment')

    properties = pika.BasicProperties(headers={'id': str(insertedItem['id']), 'action':action, 'from':'apartments'})
  
    channel.basic_publish(exchange='addapartment', routing_key='', body='Change in apartments!', properties=properties)
    
    connection.close()

def connect_to_db():
    conn = sqlite3.connect('database.db')
    return conn

def create_db_table():
    try:
        conn = connect_to_db()
        conn.execute('''
            CREATE TABLE apartments (
                id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                size INTEGER NOT NULL
            );
        ''')
        conn.commit()
        print("APARTMENTS table created successfully")
    except:
        print("APARTMENTS table creation failed - Maybe table")
    finally:
        conn.close()

def checkIfTableExist():
        conn = connect_to_db()
        cur = conn.cursor()
        listOfTables = cur.execute(
            """SELECT name FROM sqlite_master WHERE type='table'
            AND name='apartments'; """).fetchall()
        if listOfTables == []:
            return False
        else:
            return True

def insert(itemToInsert):
    inserted = {}
    try:
        conn = connect_to_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO apartments (name, size) VALUES (?, ?)", (itemToInsert['name'],   
                    itemToInsert['size']) )
        conn.commit()
        inserted = get_apartment_by_id(cur.lastrowid)
        connect_rabbit(inserted, 'add')
    except:
        conn.rollback()
    finally:
        conn.close()
    return inserted

def get_apartments():
    apartments = []
    try:
        conn = connect_to_db()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM apartments")
        rows = cur.fetchall()
        # convert row objects to dictionary
        for i in rows:
            apartment = {}
            apartment["id"] = i["id"]
            apartment["name"] = i["name"]
            apartment["size"] = i["size"]
            apartments.append(apartment)
    except:
        apartments = []
    return apartments

def get_apartment_by_id(id):
    apartment = {}
    try:
        conn = connect_to_db()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM apartments WHERE id = ?", (id,))
        row = cur.fetchone()
        # convert row object to dictionary
        apartment["id"] = row["id"]
        apartment["name"] = row["name"]
        apartment["size"] = row["size"]
    except:
        apartment = {}
    return apartment

def delete_apartment(id):
    try:
        conn = connect_to_db()
        deleted = get_apartment_by_id(id)
        conn.execute("DELETE from apartments WHERE id = ?",(id))
        conn.commit()
        connect_rabbit(deleted, 'remove')
    except:
        conn.rollback()
    finally:
        conn.close()

@app.route('/apartments/list', methods=['GET'])
def api_get_apartments():
    return jsonify(get_apartments())

@app.route('/apartments/add', methods=['POST'])
def api_add_apartment():
    if checkIfTableExist()==False:
        create_db_table()
    itemToInsert = {
        "name": request.args.get('name'), 
        "size": request.args.get('size') 
    }
    insert(itemToInsert)
    return jsonify(get_apartments())

@app.route('/apartments/remove', methods=['POST'])
def api_remove_apartment():
    delete_apartment(request.args.get('id'))
    return jsonify(get_apartments())

if __name__=='__main__':
    app.run(host='0.0.0.0', port=8080)