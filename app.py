import json
from flask_cors import CORS
import stripe
from bson import ObjectId
import json
from flask import Flask, render_template, jsonify, request
import requests
from pymongo import MongoClient
from functools import wraps
import firebase_admin
from firebase_admin import auth as firebase_auth
import time
import secrets
import hashlib

cred = firebase_admin.credentials.Certificate('jesus-shirt-project-firebase-adminsdk-o18sq-9eb6ed6989.json')
firebase_admin.initialize_app(cred)

stripe.api_key = 'sk_test_51OOBnGEvVCl2vla1w7zQ4XYBPSUslUZvifWMvfr2iji0OcoZQzfS39yYA6et6v9jKkb35D5040HdwHAvQ4fUfN7p005LTIQPJ5'

app = Flask(__name__, static_folder='public',
            static_url_path='', template_folder='public')
CORS(app, resources={r"/*": {"origins": ["http://localhost:3000", "https://jesus-shirt-shop.netlify.app","http://localhost:3001"]}})
TOKEN = "vVSC6FE0b1G4RGuBQ1EnRti9eh87a7Lc0qMlCPIy"
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {TOKEN}'
}
mongo_connection = "mongodb+srv://caleb:msl22083b@jesus-shirt-project.weyhmji.mongodb.net/mydatabase?retryWrites=true&w=majority&appName=Jesus-Shirt-Project"
client = MongoClient(mongo_connection)
shopDB = client["shop"]
productsCollection = shopDB["products"]
ordersCollection = shopDB["orders"]
usersCollection = shopDB["users"]


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)

def calculate_order_amount(items):
    # Calculate total price for items
    total_price = sum(float(item['price']) * int(item['quantity']) for item in items)
    
    # Add $2 for shipping
    total_price += 2
    return int(total_price*100)

def authenticate_firebase_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = request.headers.get('Authorization')
        request.user = None        
        if id_token and id_token.startswith('Bearer '):
            id_token = id_token.split('Bearer ')[1]
        
            try:
                decoded_token = firebase_auth.verify_id_token(id_token)
                request.user = decoded_token
                print(request)
                
                data = json.loads(request.data)

                uid = data.get("uid")
                
                if not uid:
                    return jsonify({"error":"No UID was provided"}), 400

                if uid != decoded_token["uid"]:
                    return jsonify({'error': 'UID mismatch'}), 401
            except Exception as e:
                return jsonify({'error': 'Unauthorized: Invalid token'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

def get_user_data(uid, projection):
    userData = usersCollection.find_one({"uid":uid},projection)
    return userData

def get_order_data(orderId, projection):
    orderData = ordersCollection.find_one({"order_number": orderId}, projection)
    return orderData

def generate_token(orderId):
    order_id_bytes = str(orderId).encode("utf-8")
    time_bytes = str(time.time()).encode("utf-8")
    random_bytes = secrets.token_bytes(16)
    
    token = hashlib.sha256(order_id_bytes+time_bytes+random_bytes).hexdigest()
    return token
    

@app.route('/create-payment-intent', methods=['POST'])
def create_payment():
    try:
        data = json.loads(request.data)
        # Create a PaymentIntent with the order amount and currency
        intent = stripe.PaymentIntent.create(
            amount=calculate_order_amount(data["checkoutItems"]),
            currency='sgd',
            # In the latest version of the API, specifying the `automatic_payment_methods` parameter is optional because Stripe enables its functionality by default.
            automatic_payment_methods={
                'enabled': True,
            },
        )
        # Return the client secret and PaymentIntent ID in the response
        return jsonify({
            'clientSecret': intent['client_secret'],
            'id': intent['id']
        })
    except Exception as e:
        return jsonify(error=str(e)), 403

@app.route('/fetch_product', methods=['POST'])
def handle_fetch_product():
    # Parse the JSON data from the request
    try:
        data = json.loads(request.data)
        product_id = data.get('id')
        
        if product_id is None:
            return jsonify({'error': 'Product ID is required in the request data'}), 400

        product = productsCollection.find_one({"id":product_id})

        if product:
            product = JSONEncoder().encode(product)
            return product, 200
        else:
            return jsonify({'message': 'Product not found'}), 404

    except json.JSONDecodeError as e:
        return jsonify({'error': 'Invalid JSON format in request data'}), 400
    
@app.route('/get_store-products', methods=['GET'])
def get_products():
    try:
        all_products = list(productsCollection.find())
        all_products = JSONEncoder().encode(all_products)

        result = {
            "result": all_products
        }
        return result, 200
    
    except Exception as e:  # Catching generic exceptions
        return jsonify({'error': str(e)}), 500
    
@app.route("/get-latest-order")
def get_latest_order():
    try:
        latestOrder = ordersCollection.aggregate([
            {
                "$group": {
                    "_id": None,
                    "maxOrderNumber":{"$max":"$order_number"}
                }
            }
        ])
        latestOrder = list(latestOrder)
        if len(latestOrder) != 0:
            latestOrder = JSONEncoder().encode(latestOrder[0])
            print(latestOrder)
            return latestOrder, 200
        else:
            return jsonify({'error': 'No orders found'}), 404
    except Exception as e:  # Catching generic exceptions
        return jsonify({'error': str(e)}), 500
@app.route("/update-payment-intent", methods=["POST"])    
def update_payment_intent():
    data = json.loads(request.data)
    payment_intent_id = data.get('payment_intent_id')
    shipping = data.get('shipping')
    receipt_email = data.get('receipt_email')
    try:
        stripe.PaymentIntent.modify(
            payment_intent_id,
            shipping=shipping,
            receipt_email=receipt_email,
        )

        return jsonify({'message': 'PaymentIntent updated successfully'}), 200

    except stripe.error.StripeError as e:
        print("StripeError: %s", str(e))
        return jsonify({'error': str(e)}), 500

    except Exception as e:
        print("Unexpected error: %s", str(e))
        return jsonify({'error': str(e)}), 500
    
@app.route("/place-order",methods=["POST"])
@authenticate_firebase_token
def place_order():
    try:
        data = json.loads(request.data)
        orderData = data.get("orderData")
        print('Request:',request)
        user = request.user
        if orderData["linked_user"]:
            if not user and orderData["linked_user"] != user["uid"]:
                orderData["linked_user"] = None
                
        token = generate_token(orderData["order_number"])
        orderData["order_token"] = token
        result = ordersCollection.insert_one(orderData)
        orderId = str(result.inserted_id)
        return jsonify({'message': 'Order placed successfully','orderId':orderId}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500
@app.route("/get-orders-summary",methods=["POST"])  
@authenticate_firebase_token  
def get_orders_summary():
    try:
        user = request.user
        if not user:
            return jsonify({"error":"User not authorized"}), 401
        projection = {"orders":1,"_id":0}
        userData = get_user_data(user["uid"],projection)
        if not userData:
            return jsonify({'error': 'User cannot be found'}), 404
        orderProjection = {"order_number": 1, "status": 1, "order_date": 1, "total_price": 1, "_id": 0}

        ordersList = list(map(lambda order: get_order_data(order,orderProjection), userData["orders"]))
        print(ordersList)
        if(ordersList and len(ordersList) > 0):
            return ordersList, 200
    except ValueError as ve:
        return jsonify({'error': 'Invalid JSON data'}), 400
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500  
        
@app.route("/get-order",methods=["POST"])
@authenticate_firebase_token
def get_order():
    try:
        user = request.user

        if not user:
            return jsonify({"error":"User not authorized"}), 401
        data = json.loads(request.data)
        orderNumber = data.get("orderNumber")
        userUid = data.get("uid")
        projection = {"orders": 1, "_id": 0}

        if not orderNumber or not userUid:
            return jsonify({'error': 'orderNumber and userUid are required'}), 400

        userData = get_user_data(userUid, projection)

        if isinstance(userData, dict):
            userOrders = userData['orders']

            if isinstance(userOrders, list):
                if orderNumber in userOrders:
                    orderData = get_order_data(orderNumber, None)
                    if orderData:
                        payment_method_id = orderData["payment_method"]
                        payment_method_data = stripe.PaymentMethod.retrieve(payment_method_id)
                        return jsonify({"orderData":orderData,"paymentData":payment_method_data}), 200
                    else:
                        return jsonify({'error': 'Order cannot be found'}), 404
                else:
                    return jsonify({'error': 'User not authorized to view this order'}), 403
            else:
                return jsonify({'error': 'Invalid orders format in userData'}), 500
        else:
            return jsonify({'error': 'User has not made any orders'}), 500

    except ValueError as ve:
        return jsonify({'error': 'Invalid JSON data'}), 400
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500
@app.route("/get-payment-data",methods=["POST"])
@authenticate_firebase_token
def get_payment_data():
    try:
        user = request.user

        if not user:
            return jsonify({"error":"User not authorized"}), 401
        data = json.loads(request.data)
        payment_method_id = data.get("payment_method_id")
        payment_method_data = stripe.PaymentMethod.retrieve(payment_method_id)
        return jsonify({"paymentData": payment_method_data}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route("/add-order-to-user",methods=["POST"])
@authenticate_firebase_token
def add_order_to_user():
    user = request.user

    if not user:
        return jsonify({"error":"User not authorized"}), 401
    try:
        data = json.loads(request.data)
        orderId = data.get("orderId")
        uid = data.get("uid")
        result = usersCollection.update_one({'uid': uid},{
            "$push":{
                "orders": orderId
            }
        })
        return jsonify({'message': 'Order added to user successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route("/add-user",methods=["POST"])
@authenticate_firebase_token
def add_user():
    user = request.user

    if not user:
        return jsonify({"error":"User not authorized"}), 401
    try:
        data = json.loads(request.data)
        uid = data.get("uid")
        name = data.get("name")
        email = data.get("email")
        birthday = data.get("birthday")
        clothingPreference = data.get("clothingPreference")
        usersCollection.insert_one({
            "uid":uid, 
            "name":name, 
            "email":email, 
            "birthday":birthday, 
            "clothingPreference":clothingPreference
        })
        return jsonify({'message': 'Added user successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route("/get-user",methods=["POST"])
@authenticate_firebase_token
def get_user():
    user = request.user

    if not user:
        return jsonify({"error":"User not authorized"}), 401
    try:
        data = json.loads(request.data)
        uid = data.get("uid")
        user = request.user
        projection = None
        
        userData = get_user_data(uid, projection)
        userData = JSONEncoder().encode(userData)
        
        if userData:
            return userData, 200
        else:
            return jsonify({'error': 'User cannot be found'}), 404
    except ValueError as ve:
        return jsonify({'error': 'Invalid JSON data'}), 400
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500      
if __name__ == '__main__':
    app.run(port=4242, debug=True)