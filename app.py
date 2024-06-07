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
import random
import string

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
errorDB = client["errors"]
orderErrorsCollection = errorDB["orderErrors"]

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

def generate_unique_suffix(length=8):
    # Generate a unique suffix using random letters
    return ''.join(random.choices(string.ascii_uppercase, k=length))

def generate_sequential_order_number(last_order_number):
    print("Last order number:", last_order_number)
    
    if not last_order_number:
        return "ORD00001" + generate_unique_suffix()

    # Extract the numeric part by removing non-digit characters
    numeric_part = int(''.join(filter(str.isdigit, last_order_number)))

    # Increment the numeric part to get the next order number
    next_numeric_part = numeric_part + 1

    # Combine the prefix "ORD" with the incremented numeric part, formatted to 5 digits
    next_order_number = "ORD" + str(next_numeric_part).zfill(5) + generate_unique_suffix()

    return next_order_number

def generate_sequential_error_number(last_error_number):
    print("Last error number:", last_error_number)
    
    if not last_error_number:
        return "ERR00001" + generate_unique_suffix()

    # Extract the numeric part by removing non-digit characters
    numeric_part = int(''.join(filter(str.isdigit, last_error_number)))

    # Increment the numeric part to get the next error number
    next_numeric_part = numeric_part + 1

    # Combine the prefix "ERR" with the incremented numeric part, formatted to 5 digits
    next_error_number = "ERR" + str(next_numeric_part).zfill(5) + generate_unique_suffix()

    return next_error_number


def authenticate_firebase_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = request.headers.get('Authorization')
        uid = request.args.get("uid") or request.json.get("uid")
        print("uid from auth:",uid)
        request.user = None        
        if id_token and id_token.startswith('Bearer '):
            id_token = id_token.split('Bearer ')[1]
            print("ID TOKEN:", id_token)
        
            try:
                decoded_token = firebase_auth.verify_id_token(id_token)
                request.user = decoded_token
                print(request.user)
                                
                if not uid:
                    return jsonify({"error":"No UID was provided"}), 400

                if uid != decoded_token["uid"]:
                    return jsonify({'error': 'UID mismatch'}), 401
            except Exception as e:
                if request.url_rule.rule == '/add-user':  # Adjust this condition based on your routing setup
                    firebase_auth.delete_user(uid)

                return jsonify({'error': 'Unauthorized: Invalid token'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

def get_user_data(uid, projection):
    userData = usersCollection.find_one({"uid":uid},projection)
    return userData

def get_order_data(orderId, projection):
    orderData = ordersCollection.find_one({"order_number": orderId}, projection)
    return orderData

def get_order_error_data(errorId, projection):
    errorData = orderErrorsCollection.find_one({"error_number":errorId}, projection)
    return errorData

def generate_token(orderId):
    order_id_bytes = str(orderId).encode("utf-8")
    time_bytes = str(time.time()).encode("utf-8")
    random_bytes = secrets.token_bytes(16)
    
    token = hashlib.sha256(order_id_bytes+time_bytes+random_bytes).hexdigest()
    return token
    

@app.route('/create-payment-intent', methods=['POST'])
@authenticate_firebase_token
def create_payment():
    try:
        data = json.loads(request.data)
        # Create a PaymentIntent with the order amount and currency
        user_id = None
        user = request.user
        print("/create-payment-intent:",user)

        if not user:
            user_id = None
        else:
            user_id = user["uid"]   
        checkoutItems = data.get("checkoutItems",None)
        shortenedCheckoutItems = [{"id":item["id"], "quantity":item["quantity"], "size":item["size"]} for item in checkoutItems]
        if isinstance(shortenedCheckoutItems, str) and len(shortenedCheckoutItems) > 500:
            return jsonify({"error":"Too much order items"})
        print(shortenedCheckoutItems)
        if user_id == "None":
            user_id == None
        intent = stripe.PaymentIntent.create(
            amount=calculate_order_amount(checkoutItems),
            currency='sgd',
            metadata={
                "order_items": json.dumps(shortenedCheckoutItems),
                "user_id": user_id
            }
        )
        # Return the client secret and PaymentIntent ID in the response
        return jsonify({
            'clientSecret': intent['client_secret'],
            'id': intent['id']
        })
    except Exception as e:
        print(e)
        return jsonify(error=str(e)), 403

@app.route('/fetch_product')
def handle_fetch_product():
    # Parse the JSON data from the request
    try:
        product_id = request.args.get('productID')
        
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
    projection = {"_id":0, "id":1, "name":1, "price":1,"thumbnail":1}
    try:
        all_products = list(productsCollection.find({},projection))
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
@app.route("/update-payment-intent", methods=["PUT"])    
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
def place_order():
    data = json.loads(request.data)
    orderData = data.get("orderData")
    try:
        if not orderData:
            raise ValueError("orderData is required")

        def callback(session):
            latestOrder = ordersCollection.aggregate(
                [
                    {
                        "$group": {
                            "_id": None,
                            "maxOrderNumber": {"$max": "$order_number"},
                        }
                    }
                ],
                session=session,
            )
            latestOrder = list(latestOrder)
            latestOrderNumber = (
                latestOrder[0]["maxOrderNumber"] if latestOrder else None
            )
            print(latestOrder)

            newOrderNumber = generate_sequential_order_number(latestOrderNumber)
            orderData["order_number"] = newOrderNumber
            orderData["_id"] = newOrderNumber

            token = generate_token(newOrderNumber)
            orderData["order_token"] = token

            order_insert_result = ordersCollection.insert_one(orderData, session=session)
            if not order_insert_result.acknowledged:
                raise Exception("Failed to add order to ordersCollection")

            orderId = str(order_insert_result.inserted_id)

            if orderData["linked_user"]:
                add_order_to_user_result = usersCollection.update_one(
                    {"uid": orderData["linked_user"]},
                    {"$push": {"orders": orderId}},
                    session=session,
                )
                if not add_order_to_user_result.acknowledged:
                    raise Exception("Failed to add order to user")
            payment_intent = stripe.PaymentIntent.retrieve(
                    orderData["payment_id"],
                )
            metadata = payment_intent["metadata"]
            metadata["order_id"] = orderId
            print(orderData)
            stripe.PaymentIntent.modify(
                orderData["payment_id"], metadata=metadata
            )
            raise Exception("Failed to add order to ordersCollection")

            return {
                "message": "Order placed successfully",
                "orderData": {
                    "orderNumber": orderId,
                    "address": orderData["shipping_address"],
                    "orderItems": orderData["order_items"],
                    "customer": orderData["customer"],
                },
            }

        with client.start_session() as session:
            result = session.with_transaction(callback)
            print(result)
            return jsonify({"orderResult": result}), 200

    except Exception as e:
        print(e)
        try:
            def callback(session):
                latestError = orderErrorsCollection.aggregate(
                        [{"$group": {"_id": None, "maxErrorNumber": {"$max": "$error_number"}}}],
                        session=session,
                    )
                latestError = list(latestError)
                latestErrorNumber = latestError[0]["maxErrorNumber"] if latestError else None
                newErrorNumber = generate_sequential_error_number(latestErrorNumber)
                orderData["_id"] = newErrorNumber
                orderData["error_number"] = newErrorNumber
                token = generate_token(newErrorNumber)
                orderData["order_token"] = token
                order_error_insert_result = orderErrorsCollection.insert_one(orderData, session=session)
                order_error_id = str(order_error_insert_result.inserted_id)
                payment_intent = stripe.PaymentIntent.retrieve(
                    orderData["payment_id"],
                )
                metadata = payment_intent["metadata"]
                metadata["error_number"] = order_error_id
                metadata["issue"] = "order_transaction_failed"
                stripe.PaymentIntent.modify(
                    orderData["payment_id"],
                    metadata=metadata
                )
                return jsonify({"error": str(e), "order_error_id": order_error_id}), 500

            with client.start_session() as session:
                result = session.with_transaction(callback)
                return jsonify({"errorResult": result}), 200

        except Exception as log_error:
            print(log_error)
            return jsonify({"error": str(e), "additional_error": str(log_error)}), 500

@app.route("/get-orders-summary")  
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

@app.route("/get-order-error")
def get_order_error():
    try:
        order_error_id = request.args.get("order-error-id")
        print("order error id",order_error_id)
        if not order_error_id:
            return jsonify({"error":"Order Error ID not provided"}), 400
        projection = {"order_items":1,"shipping_cost":1}
        errorData = get_order_error_data(order_error_id,projection)
        print("errorData:",errorData)
        if not errorData:
            return jsonify({"error":"Order error not found"}), 404
        else:
            return jsonify({"orderErrorInfo":errorData}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500    
        
@app.route("/get-order")
@authenticate_firebase_token
def get_order():
    try:
        user = request.user

        if not user:
            return jsonify({"error":"User not authorized"}), 401
        orderNumber = request.args.get("orderNumber")
        projection = {"orders": 1, "_id": 0}

        if not orderNumber or not user["uid"]:
            return jsonify({'error': 'orderNumber and user["uid"] are required'}), 400

        userData = get_user_data(user["uid"], projection)

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
    data = json.loads(request.data)
    uid = data.get("uid")
    name = data.get("name")
    email = data.get("email")
    birthday = data.get("birthday")
    clothingPreference = data.get("clothingPreference")
    if not user:
        return jsonify({"error":"User not authorized"}), 401
    try:
        usersCollection.insert_one({
            "uid":uid, 
            "name":name, 
            "email":email, 
            "birthday":birthday, 
            "clothingPreference":clothingPreference
        })
        return jsonify({'message': 'Added user successfully'}), 200
    except Exception as e:
        firebase_auth.delete_user(uid)
        return jsonify({'error': str(e)}), 500
@app.route("/get-user")
@authenticate_firebase_token
def get_user():
    user = request.user

    if not user:
        return jsonify({"error":"User not authorized"}), 401
    try:
        user = request.user
        projection = None
        
        userData = get_user_data(user["uid"], projection)
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
def handle_payment_intent_succeeded(payment_intent):
    print("PI metadata:",payment_intent['metadata'])
    order_data = {
        "customer": {
            "emailAddress": payment_intent['receipt_email'],
            "name": payment_intent['shipping']['name'],
        },
        "status": "printing",
        "order_items": payment_intent['metadata'].get('order_items', None),  # Fill this with actual order items if needed
        "total_price": payment_intent['amount'],
        "payment_id": payment_intent['id'],
        "shipping_address": payment_intent['shipping']['address'],
        "shipping_cost": 3.5,
        "payment_method": payment_intent['payment_method'],
        "order_date": payment_intent['created'],
        "linked_user": payment_intent['metadata'].get('user_id', None),
    }
    try:
        response = requests.post("http://127.0.0.1:4242/place-order",json={
            "orderData": order_data,
            "uid": order_data["linked_user"]
        })
        if response.status_code != 200:
            print("Failed to place order.")
            return {"error":"Failed to place order."}
        print("Order placed successfully")
        return {"success":"Order placed successfully"}
    
    except requests.RequestException as e:
        print(f"HTTP request failed: {e}")
        return {"error": "HTTP request failed"}
    
endpoint_secret = "whsec_10e8fd7fe0294f3ad3ec08186ec0ab93be59a9e646ff25b2ce1db8fe97039948"
@app.route("/stripe_webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )

    except ValueError as e:
        # Invalid payload
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return "Invalid signature", 400

    # Handle the checkout.session.completed event
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"] # contains a stripe.PaymentIntent
        res = handle_payment_intent_succeeded(payment_intent)
        if "error" in res:
            print("Order was successful.")
        else:
            print("Order was not successful")
        

    return "Success", 200   
@app.route("/retrieve-payment-intent")
def retrieve_payment_intent():
    try:
        payment_intent_id = request.args.get("payment_intent_id")
        if not payment_intent_id:
            return jsonify({"error":"Payment intent id not provided"}), 400
        payment_intent = stripe.PaymentIntent.retrieve(
                    payment_intent_id,
        )
        if not payment_intent:
            return jsonify({"error":"Payment intent not found"}), 404
        return jsonify({"paymentIntent":payment_intent}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500 

@app.route("/get-orders", methods=["POST"])
def get_orders():
    data = request.get_json()  # Correctly parse the JSON data
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    order_items = data.get("order_items")
    if isinstance(order_items, str):
        order_items = json.loads(order_items)
    print(order_items)
    if not order_items:
        return jsonify({"error": "Order items not provided"}), 400
    
    # Ensure order_items is a list of dictionaries
    if not isinstance(order_items, list) or not all(isinstance(item, dict) for item in order_items):
        return jsonify({"error": "Invalid order items format"}), 400
    
    # Extract the IDs from order_items
    order_item_ids = [item["id"] for item in order_items]
    
    projection = {"_id": 0, "id": 1, "name": 1, "price": 1, "thumbnail": 1}
    
    try:
        # Query the database with the extracted IDs
        order_data = list(productsCollection.find({"id": {"$in": order_item_ids}}, projection))
        
        if not order_data:
            return jsonify({"error": "No orders found for provided items"}), 404
        print("Before:",order_data)

        # Add quantity and size to the order_data
        for i, item in enumerate(order_items):
            for order_item in order_data:
                if order_item["id"] == item["id"]:
                    order_item["quantity"] = item["quantity"]
                    order_item["size"] = item["size"]
                    break  # Stop searching once the matching item is found
        print(order_data)
        return jsonify({"order_data": order_data}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
            
if __name__ == '__main__':
    app.run(port=4242, debug=True)