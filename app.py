import json
from flask_cors import CORS
import stripe, logging
from bson import ObjectId
import json
from flask import Flask, jsonify, request, g, abort, current_app
import requests
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from functools import wraps
import time
import secrets
import hashlib
import random
import string
import traceback
import os
from smtp2go.core import Smtp2goClient
import os
from validators import validate_fields
from supertokens_python.recipe.session.syncio import get_session
import jwt
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv, dotenv_values 
from livekit import api

load_dotenv() 
from supertokens_python import init, InputAppInfo, SupertokensConfig
from supertokens_python.recipe import thirdparty, passwordless, session
from supertokens_python.recipe.thirdparty.provider import ProviderInput, ProviderConfig, ProviderClientConfig
from supertokens_python.recipe import thirdparty

from supertokens_python.recipe.passwordless import ContactEmailOnlyConfig

from supertokens_python import get_all_cors_headers
from supertokens_python.framework.flask import Middleware

from supertokens_python.recipe.session.framework.flask import verify_session
from supertokens_python.recipe.session import SessionContainer
from supertokens_python.asyncio import delete_user
from supertokens_python.syncio import get_user as supertokens_get_user
from flask import jsonify, g
from supertokens_python.recipe.session.interfaces import SessionContainer
from supertokens_python.recipe.passwordless.interfaces import RecipeInterface
from typing import Union, Dict, Any, Optional
from supertokens_python import get_request_from_user_context
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from supertokens_python import init, InputAppInfo
from supertokens_python.recipe.passwordless.types import EmailDeliveryOverrideInput, EmailTemplateVars
from typing import Dict, Any
from supertokens_python.ingredients.emaildelivery.types import EmailDeliveryConfig

website_domain = os.getenv("WEBSITE_DOMAIN")
api_domain = os.getenv("API_DOMAIN")
dify_domain = os.getenv("DIFY_DOMAIN")

def custom_email_deliver(original_implementation: EmailDeliveryOverrideInput) -> EmailDeliveryOverrideInput:
    original_send_email = original_implementation.send_email

    async def send_email(template_vars: EmailTemplateVars, user_context: Dict[str, Any]) -> None:
        assert template_vars.url_with_link_code is not None
        request = get_request_from_user_context(user_context=user_context)
        order_id = request.get_header("orderNumber")
        state = request.get_header("state")
        order_token = request.get_header("Order-Token")
        print("Order headers", order_id, order_token)

        parsed_url = urlparse(template_vars.url_with_link_code)
        query_params = parse_qs(parsed_url.query)
        
        if order_id:
            query_params["order_id"] = order_id
        if state:
            query_params["state"] = state
        if order_token:
            query_params["order_token"] = order_token

        updated_query = urlencode(query_params, doseq=True)
        updated_url = urlunparse(parsed_url._replace(query=updated_query))
        template_vars.url_with_link_code = updated_url

        return await original_send_email(template_vars, user_context)

    original_implementation.send_email = send_email
    return original_implementation

from supertokens_python.recipe.passwordless.interfaces import (
    RecipeInterface,
)
from supertokens_python.recipe.session import SessionContainer
from supertokens_python.types import GeneralErrorResponse
from supertokens_python.recipe.passwordless.interfaces import (
    ConsumeCodeOkResult,
    ConsumeCodeIncorrectUserInputCodeError,
    ConsumeCodeExpiredUserInputCodeError,
    ConsumeCodeRestartFlowError,
)
from typing import Union, Optional, Dict, Any

def override_passwordless_functions(original_implementation: RecipeInterface):
    original_consume_code = original_implementation.consume_code

    async def consume_code(
        pre_auth_session_id: str,
        user_input_code: Union[str, None],
        device_id: Union[str, None],
        link_code: Union[str, None],
        session: Optional[SessionContainer],
        should_try_linking_with_session_user: Union[bool, None],
        tenant_id: str,
        user_context: Dict[str, Any],
    )-> Union[
        ConsumeCodeOkResult,
        ConsumeCodeIncorrectUserInputCodeError,
        ConsumeCodeExpiredUserInputCodeError,
        ConsumeCodeRestartFlowError,
        GeneralErrorResponse,
    ]:
        result = None

        try:
            # Execute the original consume_code logic
            result = await original_consume_code(
                pre_auth_session_id,
                user_input_code,
                device_id,
                link_code,
                session,
                should_try_linking_with_session_user,
                tenant_id,
                user_context,
            )
            print("Consume code result:", result.user)
            print({
                "pre_auth_session_id": pre_auth_session_id,
                "user_input_code": user_input_code,
                "device_id": device_id,
                "link_code": link_code,
                "session": session,
                "should_try_linking_with_session_user": should_try_linking_with_session_user,
                "tenant_id": tenant_id,
                "user_context": user_context,
            })

            user = result.user
            uid = user.id
            request = get_request_from_user_context(user_context=user_context)
            order_id = request.get_header("orderNumber")
            state = request.get_header("state").strip() if request.get_header("state") else None
            order_token = request.get_header("Order-Token")
            print(order_id, state, order_token, "consume code headers")

            if not user:
                raise ValueError("User is not found")

            authenticate_order_token_function(order_token=order_token, order_number=order_id)

            def callback(mongo_session):
                if result.created_new_recipe_user:
                    try:
                        usersCollection.insert_one(
                            {"uid": uid, "email": user.emails[0]},
                            session=mongo_session,
                        )
                    except Exception as e:
                        raise ValueError("Failed to insert user data into MongoDB")

                print(state in ["valid_token_unauthenticated_no_linked_user", "valid_token_authenticated_no_linked_user"], "state check for order", state, type(state))

                if state:
                    if g.order_info in ["token-invalid", "no-token-provided"]:
                        raise ValueError("Invalid order token")

                    if state in ["valid_token_unauthenticated_no_linked_user", "valid_token_authenticated_no_linked_user"]:
                        add_order_result = usersCollection.update_one(
                            {"uid": uid},
                            {"$push": {"orders": order_id}},
                            session=mongo_session,
                        )
                        if add_order_result.modified_count == 0:
                            raise ValueError("Failed to add order to user")

                        link_user_result = ordersCollection.update_one(
                            {"_id": order_id},
                            {"$set": {"linked_user": uid}},
                            session=mongo_session,
                        )
                        if link_user_result.modified_count == 0:
                            raise ValueError("Failed to link user to order")
                    else:
                        linked_user = g.order_info["linked_user"]
                        if linked_user != uid:
                            raise ValueError("The account you are trying to login does not match the one associated with order.")

            print("CREATED", result.created_new_recipe_user)
            with client.start_session() as mongo_session:
                mongo_session.with_transaction(callback)

            return result  # Return the original consume_code result on success

        except ValueError as e:
            print("ValueError during sign-up:", e)
            error_message = str(e)
            # Handle specific error cases and raise a consolidated GeneralErrorResponse
            if "Failed to insert user data into MongoDB" in error_message:
                general_error = "Oops! We couldn't save your information right now. Please try again later."
            elif error_message == "Invalid order token":
                general_error = "The order details you provided are invalid. Please check and try again."
            elif error_message == "Failed to add order to user":
                general_error = "We encountered an issue adding the order to your account. Please refresh and try again."
            elif error_message == "Failed to link user to order":
                general_error = "We couldn't link your account to the order. Please contact support for assistance."
            elif error_message == "The account you are trying to login does not match the one associated with order.":
                general_error = "It seems you're trying to log in with a different account. Please use the correct account or contact support."
            elif "User is not found" in error_message:
                general_error = "We couldn't find your account. Please make sure you're using the correct credentials."
            else:
                general_error = "An unexpected error occurred. Please try again or contact support for help."

            # Delete user and return the consolidated error
            if result and result.user and result.created_new_recipe_user:
                await delete_user(result.user.id)
                
            raise ValueError(general_error) from e

        except Exception as e:
            print("Unexpected error during sign-up:", e)
            # Handle unexpected errors
            if result and result.user and result.created_new_recipe_user:
                await delete_user(result.user.id)
            raise ValueError("An unexpected error occurred. Please try again or contact support for help.") from e

    # Override the consume_code implementation
    original_implementation.consume_code = consume_code
    return original_implementation

from supertokens_python.recipe.passwordless.interfaces import APIOptions
from supertokens_python.recipe.passwordless.interfaces import APIInterface
from supertokens_python.recipe.passwordless.asyncio import (
    list_codes_by_pre_auth_session_id,
)

def override_passwordless_apis(original_implementation: APIInterface):

    original_consume_code_post = original_implementation.consume_code_post

    async def consume_code_post(
        pre_auth_session_id: str,
        user_input_code: Union[str, None],
        device_id: Union[str, None],
        link_code: Union[str, None],
        session: Optional[SessionContainer],
        should_try_linking_with_session_user: Union[bool, None],
        tenant_id: str,
        api_options: APIOptions,
        user_context: Dict[str, Any],
    ):
        try:
            return await original_consume_code_post(
                pre_auth_session_id,
                user_input_code,
                device_id,
                link_code,
                session,
                should_try_linking_with_session_user,
                tenant_id,
                api_options,
                user_context,
            )
        except Exception as e:
            return GeneralErrorResponse(str(e))                

    original_implementation.consume_code_post = consume_code_post
    return original_implementation

init(
    app_info=InputAppInfo(
        app_name="Jesus Shirt Project",
        api_domain=api_domain,
        website_domain=website_domain,
        api_base_path="/auth",
        website_base_path="/auth"
    ),
    supertokens_config=SupertokensConfig(
        # These are the connection details of the app you created on supertokens.com
        connection_uri="https://st-dev-fa4c9ec0-a64e-11ef-b465-eb3968890c51.aws.supertokens.io",
        api_key=os.getenv("SUPERTOKENS_API_KEY")
    ),
    framework="flask",
    recipe_list=[
        session.init(), # initializes session features
        passwordless.init(
            flow_type="MAGIC_LINK",
            contact_config=ContactEmailOnlyConfig(),
            override=passwordless.InputOverrideConfig(
                functions=override_passwordless_functions,
                apis=override_passwordless_apis,
            ),
            email_delivery=EmailDeliveryConfig(override=custom_email_deliver)
        )
    ],
)


SMTP_API_TOKEN = os.getenv("SMTP-API-TOKEN")


smtp2GoClient = Smtp2goClient(api_key=SMTP_API_TOKEN)

stripe.api_key = os.getenv("STRIPE_API_KEY")
dify_api_key = os.getenv("DIFY_API_KEY")

app = Flask(
    __name__, static_folder="public", static_url_path="", template_folder="public"
)
app.config['SECRET_KEY'] = os.getenv("JWT_SECRET_KEY")
Middleware(app)

CORS(
    app,
    resources={
        r"/*": {  # Apply CORS to all routes
            "origins": [
                "http://localhost:3000",  # Frontend during development
                "https://jesus-shirt-shop.netlify.app",  # Production frontend
                "http://localhost:3001",  # Additional local frontend
                "http://localhost", # dify
                website_domain, #vercel live website
            ]
        }
    },
    supports_credentials=True,  # Required for SuperTokens sessions (cookies)
    allow_headers=["Content-Type","Order-Token","orderNumber","state","Access-Token"] + get_all_cors_headers(),  # Enable headers required by the frontend and SuperTokens
)

print(website_domain, api_domain)
@app.route('/', defaults={'u_path': ''})  
@app.route('/<path:u_path>')  
def catch_all(u_path: str):
    abort(404)
TOKEN = "vVSC6FE0b1G4RGuBQ1EnRti9eh87a7Lc0qMlCPIy"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
mongo_connection = os.getenv("MONGO_CONNECTION")
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


def get_full_order_data(order_items, projection):
    print("item from get-full-order-data",order_items)
    # Extract the IDs from order_items
    order_item_ids = [item["id"] for item in order_items]
    order_data = list(
        productsCollection.find({"id": {"$in": order_item_ids}}, projection)
    )

    if not order_data:
        print({"error": "No orders found for provided items"})
        return {"error": "No orders found for provided items"}

    final_order_data = []
    for item in order_items:
        for order_item in order_data:
            if order_item["id"] == item["id"]:
                # Create a new entry for each unique combination
                new_order_item = order_item.copy()  # Create a copy of the order_item
                new_order_item["quantity"] = item["quantity"]
                new_order_item["size"] = item["size"]
                final_order_data.append(new_order_item)
    print("success,", final_order_data)
    return {"result": final_order_data}

def handle_send_email(client, payload):
    response = client.send(**payload)
    if response.success: 
        print(response.json)
        return {"status":"success","data":response.json}
    else:
        print(response.errors)
        return {"status":"error","error":response.errors}
    
def calculate_order_amount(items):
    projection = {"_id": 0, "price": 1, "id":1}

    fullDataItems = get_full_order_data(items, projection)
    if "error" in fullDataItems:
        return {"error": fullDataItems["error"]}
    # Calculate total price for items
    total_price = sum(
        float(item["price"]) * int(item["quantity"]) for item in fullDataItems["result"]
    )

    # Add $2 for shipping
    total_price += 2
    return int(total_price * 100)


def generate_unique_suffix(length=4):
    # Generate a unique alphanumeric suffix
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def generate_sequential_order_number(last_order_number):
    print("Last order number:", last_order_number)

    if not last_order_number:
        return "ORD00001" + generate_unique_suffix()

    # Extract the numeric part by removing non-digit characters
    numeric_part = int("".join(filter(str.isdigit, last_order_number)))

    # Increment the numeric part to get the next order number
    next_numeric_part = numeric_part + 1

    # Combine the prefix "ORD" with the incremented numeric part, formatted to 5 digits
    next_order_number = (
        "ORD" + str(next_numeric_part).zfill(5) + generate_unique_suffix()
    )

    return next_order_number


def generate_jwt(user_id):
    """
    Generate a JWT for the user.
    """
    now = datetime.now(timezone.utc)
    payload = {
        'user_id': user_id,
        'exp': int((now + timedelta(minutes=15)).timestamp()),
        'iat': int(now.timestamp())
    }
    print("now type:", type(now), "value:", now)
    print("timedelta type:", type(timedelta(minutes=15)), "value:", timedelta(minutes=15))

    result = now + timedelta(minutes=15)
    print("result type:", type(result), "value:", result)
    secret_key = current_app.config['SECRET_KEY']
    return jwt.encode(payload, secret_key, algorithm='HS256')

def validate_jwt(token):
    """
    Validate the JWT and return the decoded payload.
    """
    secret_key = current_app.config['SECRET_KEY']
    try:
        decoded = jwt.decode(token, secret_key, algorithms=['HS256'])
        return decoded  # Contains 'user_id', 'exp', etc.
    except jwt.ExpiredSignatureError:
        return None  # Token has expired
    except jwt.InvalidTokenError:
        return None  # Token is invalid

def generate_sequential_error_number(last_error_number):
    print("Last error number:", last_error_number)

    if not last_error_number:
        return "ERR00001" + generate_unique_suffix()

    # Extract the numeric part by removing non-digit characters
    numeric_part = int("".join(filter(str.isdigit, last_error_number)))

    # Increment the numeric part to get the next error number
    next_numeric_part = numeric_part + 1

    # Combine the prefix "ERR" with the incremented numeric part, formatted to 5 digits
    next_error_number = (
        "ERR" + str(next_numeric_part).zfill(5) + generate_unique_suffix()
    )

    return next_error_number

def authenticate_order_token_function(order_token, order_number):
    g.order_info = "token-invalid"

    if order_token == "null" or not order_token:
        order_token = None
    
    print("Order id:", order_number)

    if order_token:
        try:
            order_data = json.loads(get_order_data(order_number, None))
            if not order_data:
                return jsonify({"error": "Failed to fetch order token"}), 400
            order_token_from_db = order_data.get("order_token", None) if order_data else None
            print("order_token_from_db:", order_token_from_db, "order_token_from_frontend:", order_token)
            if order_data and order_token_from_db == order_token:
                g.order_info = order_data
            else:
                g.order_info = "token-invalid"
        except json.JSONDecodeError as e:
            print("JSON decode error:", str(e))
            g.order_info = "token-invalid"
        except Exception as e:
            print("Unexpected error:", str(e))
            g.order_info = "token-invalid"
    else:
        g.order_info = "no-token-provided"

    return g.order_info

def authenticate_order_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print("json payload get_order:",request.args)

        g.order_info = "token-invalid"
        order_token = request.headers.get('Order-Token')
        order_id = request.args.get("orderNumber") or (request.json and request.json.get("orderNumber"))
        if order_token == "null" or not order_token:
            order_token = None
            
        print("Order id:",order_id)    

        if order_token:
            try:
                order_data = json.loads(get_order_data(order_id, None))
                if not order_data:
                    return jsonify({"error":"Failed to fetch order token"}), 400
                order_token_from_db = order_data.get("order_token",None) if order_data else None
                print("order_token_from_db:", order_token_from_db, "order_token_from_frontend:",order_token)
                if order_data and order_token_from_db == order_token:
                    g.order_info = order_data
                else:
                    g.order_info = "token-invalid"
            except json.JSONDecodeError as e:
                print("JSON decode error:", str(e))
                g.order_info = "token-invalid"
            except Exception as e:
                print("Unexpected error:", str(e))
                g.order_info = "token-invalid"
        else:
            g.order_info = "no-token-provided"

        return f(*args, **kwargs)


    return decorated_function


def get_user_data(uid, projection):
    userData = usersCollection.find_one({"uid": uid}, projection)
    print("uid",uid)
    return userData if userData else {}


def get_order_data(orderId, projection):
    orderData = ordersCollection.find_one({"order_number": orderId}, projection)
    return json.dumps(orderData)


def get_order_error_data(errorId, projection):
    errorData = orderErrorsCollection.find_one({"error_number": errorId}, projection)
    return errorData

def get_linked_user(orderNumber):
    linkedUserFromDBRes = json.loads(get_order_data(orderNumber, {"linked_user":1,"_id":0}))
    linkedUserFromDB = linkedUserFromDBRes["linked_user"] if linkedUserFromDBRes and linkedUserFromDBRes["linked_user"] else None
    return json.dumps(linkedUserFromDB)


def generate_token(orderId):
    order_id_bytes = str(orderId).encode("utf-8")
    time_bytes = str(time.time()).encode("utf-8")
    random_bytes = secrets.token_bytes(16)

    token = hashlib.sha256(order_id_bytes + time_bytes + random_bytes).hexdigest()
    return token

def is_dict_empty(d):
    return not bool(d)

def get_session_and_user_id(request):
    user_id = None
    session = None
    try:
        session = get_session(request)
        print("SESSION PRINT",session)
    except Exception as e:
        print("Error while fetching session:", str(e))

    # Create a PaymentIntent with the order amount and currency
    print("SESSION:", session)
    if session is not None:
        try:
            user_id = session.get_user_id()
        except Exception as e:
            print("Error while fetching user ID:", str(e))
    return user_id, session      


@app.route("/create-payment-intent", methods=["POST"])
def create_payment():
    try:
        data = json.loads(request.data)
        user_id,_=get_session_and_user_id(request)

        checkoutItems = data.get("checkoutItems", None)
        shortenedCheckoutItems = [
            {"id": item["id"], "quantity": item["quantity"], "size": item["size"]}
            for item in checkoutItems
        ]
        if len(shortenedCheckoutItems) > 20:
            return jsonify({"error": "Too much order items"})
        print("order amount:",calculate_order_amount(shortenedCheckoutItems))    
        intent = stripe.PaymentIntent.create(
            amount=calculate_order_amount(shortenedCheckoutItems),
            currency="sgd",
            metadata={
                "order_items": json.dumps(shortenedCheckoutItems),
                "user_id": user_id,
                "shipping_cost": 3.5,
                "orderStatus": "processing",
            },
        )
        # Return the client secret and PaymentIntent ID in the response
        return jsonify({"clientSecret": intent["client_secret"], "id": intent["id"]})
    except stripe.error.CardError as e:
        charge = stripe.Charge.retrieve(e.error.payment_intent.latest_charge)
        if charge.outcome.type == "blocked":
            logging.error("Payment blocked for suspected fraud.")
        elif e.code == "card_declined":
            logging.error("Payment declined by the issuer.")
        elif e.code == "expired_card":
            logging.error("Card expired.")
        else:
            logging.error("Other card error.")
            
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        print("error from create-payment-intent:",e)
        return jsonify({"error": str(e)}), 500


@app.route("/fetch_product")
def handle_fetch_product():
    projection = {"_id": 0, "id": 1, "name": 1, "price": 1, "thumbnail": 1,"product_images":1}

    try:
        product_id = request.args.get("productID")

        if product_id is None:
            return jsonify({"error": "Product ID is required in the request data"}), 400

        product = productsCollection.find_one({"id": product_id},projection=projection)

        if product:
            product = JSONEncoder().encode(product)
            return product, 200
        else:
            return jsonify({"message": "Product not found"}), 404

    except json.JSONDecodeError as e:
        return jsonify({"error": "Invalid JSON format in request data"}), 400


@app.route("/get_store_products", methods=["GET"])
def get_products():
    projection = {"_id": 0, "id": 1, "name": 1, "price": 1, "thumbnail": 1,"product_images":1}
    try:
        all_products = list(productsCollection.find({}, projection))
        print(all_products)
        if not all_products:
            return jsonify({"error": "No products found."}), 404

        return jsonify(all_products), 200

    except Exception as e:
        return jsonify({"error": "An unexpected error occurred while fetching the products."}), 500


@app.route("/get-latest-order")
def get_latest_order():
    try:
        latestOrder = ordersCollection.aggregate(
            [{"$group": {"_id": None, "maxOrderNumber": {"$max": "$order_number"}}}]
        )
        latestOrder = list(latestOrder)
        if len(latestOrder) != 0:
            latestOrder = jsonify(latestOrder[0])
            print(latestOrder)
            return latestOrder, 200
        else:
            return jsonify({"error": "No orders found"}), 404
    except Exception as e:  # Catching generic exceptions
        return jsonify({"error": str(e)}), 500


@app.route("/update-payment-intent", methods=["PUT"])
def update_payment_intent():
    data = json.loads(request.data)
    payment_intent_id = data.get("payment_intent_id")
    shipping = data.get("shipping")
    receipt_email = data.get("receipt_email")
    try:
        stripe.PaymentIntent.modify(
            payment_intent_id,
            shipping=shipping,
            receipt_email=receipt_email,
        )

        return jsonify({"message": "PaymentIntent updated successfully"}), 200

    except stripe.error.StripeError as e:
        print("StripeError: %s", str(e))
        return jsonify({"error": str(e)}), 500

    except Exception as e:
        print("Unexpected error: %s", str(e))
        return jsonify({"error": str(e)}), 500


def update_stripe_metadata(payment_id, metadata):
    stripe.PaymentIntent.modify(payment_id, metadata=metadata)

def process_order(session, orderData):
    latestOrder = list(ordersCollection.aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "maxOrderNumber": {"$max": "$order_number"},
                }
            }
        ],
        session=session
    ))
    latestOrderNumber = latestOrder[0]["maxOrderNumber"] if latestOrder else None

    newOrderNumber = generate_sequential_order_number(latestOrderNumber)
    orderData["order_number"] = newOrderNumber
    orderData["_id"] = newOrderNumber

    token = generate_token(newOrderNumber)
    orderData["order_token"] = token

    order_insert_result = ordersCollection.insert_one(orderData, session=session)
    if not order_insert_result.acknowledged:
        raise Exception("Failed to add order to ordersCollection")

    orderId = str(order_insert_result.inserted_id)

    if orderData.get("linked_user"):
        add_order_to_user_result = usersCollection.update_one(
            {"uid": orderData["linked_user"]},
            {"$push": {"orders": orderId}},
            session=session,
        )
        if not add_order_to_user_result.acknowledged:
            raise Exception("Failed to add order to user")

    payment_intent = stripe.PaymentIntent.retrieve(orderData["payment_id"])
    metadata = payment_intent["metadata"]
    metadata.update({"order_id": orderId, "orderStatus": "success"})
    print("metadata:",metadata)
    update_stripe_metadata(orderData["payment_id"], metadata)
    
    email_payload = {
    "sender": "tan_xuan_yi_caleb@students.edu.sg",
    "recipients": [orderData["customer"]["emailAddress"]],
    "template_id": "8449130",
    "template_data": {
        "product_name": "Jesus-Shirt-Project",
        "orders_url": f'{website_domain}/orders/{orderData["order_number"]}?order_token={orderData["order_token"]}',
        "payment": orderData["payment_id"],
        "shipping": orderData["shipping_cost"],
        "email": orderData["customer"]["emailAddress"],
        "address_line_name": orderData["customer"]["name"],
        "address_line_street": orderData["shipping_address"]["line1"],
        "address_line_city": orderData["shipping_address"]["city"],
        "address_line_state_country": orderData["shipping_address"]["state"] + ", " + orderData["shipping_address"]["country"],
        "order_id": orderData["_id"],
        "items": orderData["order_items"],
        "total": orderData["total_price"]
    },
}
 
    emailRes = handle_send_email(smtp2GoClient, email_payload)
    print("emailRes",emailRes)
    if emailRes["status"] != "success":
        raise Exception("Failed to send email to customer")

    return {
        "message": "Order placed successfully",
        "orderData": {
            "orderNumber": orderId,
            "address": orderData["shipping_address"],
            "orderItems": orderData["order_items"],
            "customer": orderData["customer"],
        },
    }

def handle_order_error(session, orderData, error):
    print("handle_order_error:",error)
    latestError = list(orderErrorsCollection.aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "maxErrorNumber": {"$max": "$error_number"},
                }
            }
        ],
        session=session
    ))
    latestErrorNumber = latestError[0]["maxErrorNumber"] if latestError else None
    newErrorNumber = generate_sequential_error_number(latestErrorNumber)
    orderData["_id"] = newErrorNumber
    orderData["error_number"] = newErrorNumber

    token = generate_token(newErrorNumber)
    orderData["order_token"] = token

    order_error_insert_result = orderErrorsCollection.insert_one(orderData, session=session)
    order_error_id = str(order_error_insert_result.inserted_id)

    payment_intent = stripe.PaymentIntent.retrieve(orderData["payment_id"])
    metadata = payment_intent["metadata"]
    metadata.update({"error_number": order_error_id, "issue": "order_transaction_failed", "orderStatus": "failed"})
    update_stripe_metadata(orderData["payment_id"], metadata)

    return {"error": str(error), "order_error_id": order_error_id}
    
@app.route("/place-order", methods=["POST"])
def place_order():
    data = json.loads(request.data)
    orderData = data.get("orderData")

    if not orderData:
        return jsonify({"error": "orderData is required"}), 400

    try:
        with client.start_session() as session:
            result = session.with_transaction(lambda s: process_order(s, orderData))
            print("Place Order Success!")
            return jsonify({"orderResult": result}), 200

    except Exception as e:
        print(traceback.format_exc())
        try:
            with client.start_session() as session:
                error_result = session.with_transaction(lambda s: handle_order_error(s, orderData, e))
                return jsonify({"errorResult": error_result}), 500
        except Exception as log_error:
            print(traceback.format_exc())
            return jsonify({"error": str(e), "additional_error": str(log_error)}), 500

@app.route("/get-orders-summary")
@verify_session()
def get_orders_summary():
    try:
        session: SessionContainer = g.supertokens
        user_id = session.get_user_id()  
        print("User ID:", user_id)      

        projection = {"orders": 1, "_id": 0, "uid": 1}
        userData = get_user_data(user_id, projection)
        print("userData",userData)
        if userData is None or is_dict_empty(userData):
            return jsonify({"error": "User cannot be found"}), 404
        
        if "orders" not in userData:
            return jsonify({"orders": []}), 200
        
        orderProjection = {
            "order_number": 1,
            "status": 1,
            "order_date": 1,
            "total_price": 1,
            "_id": 0,
        }

        ordersList = [
            json.loads(get_order_data(order, orderProjection)) for order in userData["orders"]
        ]
        print("Orders List:", ordersList)
        
        if ordersList:
            return jsonify({"orders": ordersList}), 200
        else:
            return jsonify({"orders": []}), 200

    except ValueError as ve:
        return jsonify({"error": "Invalid JSON data"}), 400
    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/test-superbase',methods=["POST"])
@verify_session()
def test_superbase():
    return jsonify({"message": "Session is valid!"})

@app.route("/get-order-error")
def get_order_error():
    try:
        order_error_id = request.args.get("order-error-id")
        print("order error id", order_error_id)
        if not order_error_id:
            return jsonify({"error": "Order Error ID not provided"}), 400
        projection = {"order_items": 1, "shipping_cost": 1}
        errorData = get_order_error_data(order_error_id, projection)
        print("errorData:", errorData)
        if not errorData:
            return jsonify({"error": "Order error not found"}), 404
        else:
            return jsonify({"orderErrorInfo": errorData}), 200
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500

def determine_order_state(order_token_verified, is_authenticated, has_linked_user, order_error, linked_user_email, order_number, order_token):
    """
    Determine the appropriate state and action for the order flow.
    
    Args:
        order_token_verified (str): Status of order token verification 
        is_authenticated (bool): Whether the user is authenticated
        has_linked_user (bool): Whether the order has a linked user
        order_error (bool): Whether there's an order-related error
        linked_user_email (str): Email of the linked user
    
    Returns:
        dict: Contains state, redirect information, and message
    """
    # Case 1: Invalid or Missing orderToken
    if order_token_verified in ["no-token-provided", "token-invalid"]:
        if has_linked_user:
            # Case 1a: Has Linked User
            if order_error:
                return {
                    "state": "token_invalid_linked_user",
                    "redirect": "/auth",
                    "message": f"Login to the account linked with this order to view it."
                }
            else:
                return {
                    "state": "token_invalid_linked_user",
                    "action": "display_order"
                }
        else:
            # Case 1b: No Linked User
            return {
                "state": "token_invalid_no_linked_user",
                "redirect": "/resend_order_link",
                "action": "resend_order_link",
                 "message": "Your order token is missing or invalid. You can resend the order link to your registered email.",
            }
    
    # Case 2: Valid orderToken
    if not is_authenticated:
        # Scenario 2a: Unauthenticated User
        if has_linked_user:
            return {
                "state": "valid_token_unauthenticated_linked_user",
                "redirect": "/auth",
                "linkedUserEmail": linked_user_email,
                "message": f"Login to the account linked with this order ({linked_user_email}) to view it.",
            }
        else:
            return {
                "state": "valid_token_unauthenticated_no_linked_user", 
                "redirect": "/auth",
                 "message": "Sign up to connect this order to your account.",
            }
    
    # Scenario 2b: Authenticated User
    if has_linked_user:
        if order_error:
            return {
                "state": "valid_token_authenticated_order_error",
                "redirect": "/auth", 
                "linkedUserEmail": linked_user_email,
                "message": f"This order is linked to another account ({linked_user_email}). Please log in with the correct account.",
            }
        else:
            return {
                "state": "valid_token_authenticated_no_order_error",
                "action": "display_order"
            }
    else:
        return {
            "state": "valid_token_authenticated_no_linked_user",
            "redirect": f"/link-order",
            "message": "Connect this order to your account."
        }

@app.route("/get-order", methods=["POST", "GET"])
@authenticate_order_token
def get_order():
    try:
        # First part: Original `get_order` functionality
        #either use access token from supertokens
        print("json payload get_order:",request.args)
        user_id, _ = get_session_and_user_id(request)
        user_id_from_dify = request.args.get("user_id_from_dify")
        #or use temporary access token passed to dify
        jwt_payload = validate_jwt(request.headers.get("Access-Token"))
        if user_id == None:
            if jwt_payload and jwt_payload.get("user_id") == user_id_from_dify:
                user_id = jwt_payload.get("user_id") if jwt_payload else None
            
        print("user_id from get-order",user_id)    
        projection = {"orders": 1, "_id": 0}
        
        # Fetch necessary data
        userData = get_user_data(user_id, projection)
        orderNumber = request.args.get("orderNumber") if request.method == "GET" else None
        linkedUserFromDB = json.loads(get_linked_user(orderNumber))
        userOrders = userData.get("orders", [])
        
        if not orderNumber:
            return jsonify({"error": "No order number is provided"}), 403
        
        # Order token verification
        orderInfo = g.get("order_info", None)
        order_token_verified = (
            "no-token-provided" if orderInfo == "no-token-provided"
            else "token-invalid" if orderInfo == "token-invalid"
            else "token-verified"
        )
        
        # Prepare data for state determination
        is_authenticated = bool(user_id)
        has_linked_user = linkedUserFromDB is not None
        order_error = (
            not is_authenticated or 
            orderNumber not in userOrders or 
            (has_linked_user and linkedUserFromDB != user_id)
        )
        
        # Fetch linked user email
        linkedUserEmail = None
        if order_token_verified == "token-verified" and has_linked_user:
            linkedUserInfo = get_user_data(linkedUserFromDB, {"email": 1, "_id": 0})
            print(linkedUserInfo)
            linkedUserEmail = linkedUserInfo.get("email")
        
        # Determine order flow state
        order_state = determine_order_state(
            order_token_verified, 
            is_authenticated, 
            has_linked_user, 
            order_error, 
            linkedUserEmail,
            orderNumber,
            order_token = request.headers.get('Order-Token')
        )
        
        # Handle different states
        if "redirect" in order_state:
            print({ "linkedUserEmail": order_state.get("linkedUserEmail")})
            return jsonify({
                "error": "An error occurred when fetching order",
                "state": order_state["state"],
                "redirect": order_state["redirect"],
                "linkedUserEmail": order_state.get("linkedUserEmail"),
                "orderNumber":orderNumber
            }), 401 if "auth" in order_state["redirect"] else 403
        
        # If action is to display order
        if order_state.get("action") == "display_order":
            orderData = orderInfo if orderInfo not in ["no-token-provided", "token-invalid"] else json.loads(get_order_data(orderNumber, None))
            
            if not orderData:
                return jsonify({"error": "Order cannot be found"}), 404
            
            payment_method_id = orderData["payment_method"]
            payment_method_data = stripe.PaymentMethod.retrieve(payment_method_id) if not user_id_from_dify else None
            
            # Second part: Integrate `get_orders` functionality
            order_items = orderData["order_items"]
            if isinstance(order_items, str):
                order_items = json.loads(order_items)
            if not order_items:
                return jsonify({"error": "Order items not provided"}), 400

            # Ensure order_items is a list of dictionaries
            if not isinstance(order_items, list) or not all(
                isinstance(item, dict) for item in order_items
            ):
                return jsonify({"error": f"Invalid order items format {order_items}"}), 400
            projection = {"_id": 0, "id": 1, "name": 1, "price": 1, "thumbnail": 1}

            try:
                final_order_data = get_full_order_data(order_items, projection)
                if "error" in final_order_data:
                    return jsonify({"error": final_order_data["error"]}), 404

                orderData["full_order_items"] = final_order_data["result"]
                cleaned_order_data = {
                    "customer": {
                        "emailAddress": orderData["customer"]["emailAddress"],
                        "name": orderData["customer"]["name"]
                    },
                    "full_order_items": [
                        {
                            "name": item["name"],
                            "price": item["price"],
                            "quantity": item["quantity"],
                            "size": item["size"],
                            "thumbnail": item["thumbnail"]
                        } for item in orderData["full_order_items"]
                    ],
                    "order_date": orderData["order_date"],
                    "order_number": orderData["order_number"],
                    "shipping_address": {
                        "city": orderData["shipping_address"]["city"],
                        "country": orderData["shipping_address"]["country"],
                        "line1": orderData["shipping_address"]["line1"],
                        "postal_code": orderData["shipping_address"]["postal_code"]
                    },
                    "status": orderData["status"],
                    "total_price": orderData["total_price"]
                }
                return jsonify({
                    "orderData": orderData,
                    "paymentData": payment_method_data,
                    "orderTokenVerified": order_token_verified,
                    "state": order_state["state"],
                } if not user_id_from_dify else {"orderData": cleaned_order_data}), 200
            except Exception as e:
                return jsonify({"error": str(e)}), 500
    
    except ValueError as ve:
        print(traceback.format_exc())
        return jsonify({"error": "Invalid JSON data"}), 400
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/link-order", methods=["POST"])
@verify_session()
@authenticate_order_token
def add_user():
    super_token_session: SessionContainer = g.supertokens 

    uid = super_token_session.get_user_id()
  
    data = request.get_json()
    user = supertokens_get_user(uid)
    
    orderId = data.get('orderNumber', None)
    linkedUserFromDB = json.loads(get_linked_user(orderId))
    
    if linkedUserFromDB:
        return jsonify({"error":"Order already has a linked user"}),401

    try:
        if not data:
            raise ValueError("No data provided")
        if not user:
            raise ValueError("User is not found")
        def callback(session):
            if g.order_info in ["token-invalid", "no-token-provided"]:
                print("g.order_info:", g.order_info)
                raise ValueError("Invalid order token")

            try:
                addOrderToUserResult = usersCollection.update_one(
                    {"uid": uid},
                    {"$push": {"orders": orderId}},
                    session=session
                )
                if addOrderToUserResult.modified_count == 0:
                    raise ValueError("Failed to add order to user")
            except Exception as e:
                raise ValueError("Failed to update user's orders: " + str(e))

            try:
                addUserToOrder = ordersCollection.update_one(
                    {"_id": orderId},
                    {"$set": {"linked_user": uid}},
                    session=session
                )
                if addUserToOrder.modified_count == 0:
                    raise ValueError("Failed to add user to order")
            except Exception as e:
                raise ValueError("Failed to link user to order: " + str(e))

        with client.start_session() as session:
            session.with_transaction(callback)
            return jsonify({"message": "Transaction successful"}), 200

    except ValueError as e:
        print("ValueError during sign up:", e)
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        print("Unexpected error during sign up:", e)
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500

@app.route("/send-order-link", methods=["POST"])
def resend_order_link():
    data = request.get_json()

    # Check if the required fields (orderNumber and email) are present
    orderNumber = data.get("orderNumber")
    email = data.get("email")
    if not email or not orderNumber:
        return jsonify({"error": "Please provide both your email and order number to proceed."}), 400

    try:
        # Generate a new token for the order
        newToken = generate_token(orderNumber)

        # Update the order in MongoDB with the new token
        update_result = ordersCollection.update_one({"_id": orderNumber}, {"$set": {"order_token": newToken}})
        
        # If no documents were updated, return an error
        if update_result.matched_count == 0:
            return jsonify({"error": "Order not found. Please check the order number and try again."}), 404

        # Fetch the order data
        raw_order_data = get_order_data(orderNumber, {})
        if not raw_order_data:
            return jsonify({"error": "If the details provided are correct, you will receive a link shortly."}), 404

        orderData = json.loads(raw_order_data)
        emailFromOrder = orderData.get("customer", {}).get("emailAddress")
        
        # Check if the email is present in the order data
        if not emailFromOrder:
            return jsonify({"error": "We encountered an issue retrieving your order information. Please try again later."}), 500

        # Validate email with the one provided
        if email != emailFromOrder:
            return jsonify({"error": "The provided email does not match the one used during checkout. Please check and try again."}), 400

        # Prepare email payload for sending
        email_payload = {
            "sender": "tan_xuan_yi_caleb@students.edu.sg",
            "recipients": [email],
            "template_id": "8449130",
            "template_data": {
                "product_name": "Jesus-Shirt-Project",
                "orders_url": f'{website_domain}/orders/{orderData["order_number"]}?order_token={orderData["order_token"]}',
                "payment": orderData["payment_id"],
                "shipping": orderData["shipping_cost"],
                "email": emailFromOrder,
                "address_line_name": orderData["customer"]["name"],
                "address_line_street": orderData["shipping_address"]["line1"],
                "address_line_city": orderData["shipping_address"]["city"],
                "address_line_state_country": f'{orderData["shipping_address"]["state"]}, {orderData["shipping_address"]["country"]}',
                "order_id": orderData["_id"],
                "items": orderData["order_items"],
                "total": orderData["total_price"],
            },
        }

        # Send the email
        """
        emailRes = handle_send_email(smtp2GoClient, email_payload)
        
        # Check if the email was sent successfully
        if emailRes.get("status") != "success":
            return jsonify({"error": "We couldn't send the email at this time. Please try again later."}), 500
        """
        return jsonify({"message": "A new order link has been sent to your email."}), 200

    except KeyError as e:
        return jsonify({"error": f"Missing required field: {str(e)}. Please try again later."}), 400
    except Exception as e:
        print(e)
        return jsonify({"error": f"An unexpected error occurred. Please try again later."}), 500

def handle_payment_intent_succeeded(payment_intent):
    print("PI metadata:", payment_intent["metadata"])
    order_data = {
        "customer": {
            "emailAddress": payment_intent["receipt_email"],
            "name": payment_intent["shipping"]["name"],
        },
        "status": "printing",
        "order_items": payment_intent["metadata"].get(
            "order_items", None
        ),  # Fill this with actual order items if needed
        "total_price": payment_intent["amount"],
        "payment_id": payment_intent["id"],
        "shipping_address": payment_intent["shipping"]["address"],
        "shipping_cost": payment_intent["metadata"].get("shipping_cost", None),
        "payment_method": payment_intent["payment_method"],
        "order_date": payment_intent["created"],
        "linked_user": payment_intent["metadata"].get("user_id", None),
    }

    try:
        response = requests.post(
            f"{api_domain}/place-order",
            json={"orderData": order_data, "uid": order_data["linked_user"]},
        )
        if response.status_code != 200:
            print("Failed to place order.")
            return {"error": "Failed to place order."}
        print("Order placed successfully")
        return {"success": "Order placed successfully"}

    except requests.RequestException as e:
        print(f"HTTP request failed: {e}")
        return {"error": "HTTP request failed"}


endpoint_secret = os.getenv("STRIPE_ENDPOINT_SECRET")


@app.route("/stripe_webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")
    print("Webhook triggered")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)

    except ValueError as e:
        # Invalid payload
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return "Invalid signature", 400

    # Handle the checkout.session.completed event
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]  # contains a stripe.PaymentIntent
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
            return jsonify({"error": "Payment intent id not provided"}), 400
        payment_intent = stripe.PaymentIntent.retrieve(
            payment_intent_id,
        )
        if not payment_intent:
            return jsonify({"error": "Payment intent not found"}), 404
        return jsonify({"paymentIntent": payment_intent}), 200
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500


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
    if not isinstance(order_items, list) or not all(
        isinstance(item, dict) for item in order_items
    ):
        return jsonify({"error": f"Invalid order items format {order_items}"}), 400
    projection = {"_id": 0, "id": 1, "name": 1, "price": 1, "thumbnail": 1}

    try:
        final_order_data = get_full_order_data(order_items, projection)
        if "error" in final_order_data:
            return jsonify({"error": final_order_data["error"]}), 404

        return jsonify({"order_data": final_order_data["result"]}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route('/send-dify-chat-message', methods=['POST'])
def send_dify_chat_message():
    DIFY_API_URL = f"{dify_domain}/v1/chat-messages"
    user_id, session = get_session_and_user_id(request)

    # Get the user ID and other inputs from the request body
    query = request.json.get('query')
    inputs = request.json.get('inputs', {}) ## to pass jwt
    conversation_id = request.json.get('conversation_id',"")

    # Add the access_token to the inputs
    if user_id != None and session != None:
        inputs['access_token'] = generate_jwt(user_id)
    print("Inputs",inputs)
    # Prepare the request payload
    payload = {
        "query": query,
        "inputs": inputs,
        "response_mode": "blocking",
        "user": generate_guest_uid() if not user_id else user_id,
        "conversation_id": conversation_id,
    }
    
    print("Payload:",payload)

    # Set the headers with the Dify API key for authentication
    headers = {
        'Authorization': f'Bearer {dify_api_key}',  # Use the API key directly in the header
        'Content-Type': 'application/json'
    }

    try:
        # Make the POST request to the Dify API
        response = requests.post(DIFY_API_URL, json=payload, headers=headers)
        # Check if the request was successful
        if response.status_code == 200:
            data = response.json()
            print(data["answer"])
            return jsonify({"answer":data["answer"],"conversation_id":data["conversation_id"]}), 200  # Return the response from the Dify API
        else:
            print(response.text)
            return jsonify({"error": "Failed to send message"}), response.status_code

    except Exception as e:
        print("error from dify", str(e))
        return jsonify({"error": str(e)}), 500
    
@app.route('/get_connection_details', methods=['GET'])
def get_connection_details():
    try:
        LIVEKIT_URL = os.getenv("LIVEKIT_URL")
        API_KEY = os.getenv("LIVEKIT_API_KEY")
        API_SECRET = os.getenv("LIVEKIT_API_SECRET")
        
        user_id, session = get_session_and_user_id(request)
        
        short_lived_jwt = None
        
        if user_id != None and session != None:
            short_lived_jwt = generate_jwt(user_id)
            
        print("short lived jwt",short_lived_jwt)    

        if not LIVEKIT_URL:
            raise ValueError("LIVEKIT_URL is not defined")
        if not API_KEY:
            raise ValueError("LIVEKIT_API_KEY is not defined")
        if not API_SECRET:
            raise ValueError("LIVEKIT_API_SECRET is not defined")

        # Generate participant identity and room name
        guest_participant_identity = f"guest_user_{random.randint(0, 9999)}"
        room_name = f"voice_assistant_room_{random.randint(0, 9999)}"

        # Generate participant token
        participant_token = create_participant_token({"identity": user_id if user_id else guest_participant_identity}, room_name, short_lived_jwt)
        print("jwt token:", participant_token) 
        # Return connection details
        data = {
            "serverUrl": LIVEKIT_URL,
            "roomName": room_name,
            "participantToken": participant_token,
            "participantName": user_id if user_id else guest_participant_identity,
        }
        return jsonify(data), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def create_participant_token(user_info, room_name, short_lived_jwt):
    API_KEY = os.getenv("LIVEKIT_API_KEY")
    API_SECRET = os.getenv("LIVEKIT_API_SECRET")
    try:
        token = api.AccessToken(API_KEY, API_SECRET) \
        .with_identity(user_info.get("identity", "default_identity")) \
        .with_ttl(900)  \
        .with_metadata(json.dumps({"access_token":short_lived_jwt})) \

        # Add video grants
        grants = api.VideoGrants(
            room=room_name,
            room_join=True,
            can_publish=True,
            can_publish_data=True,
            can_subscribe=True
        )
        token.with_grants(grants)
        print("Livekit token",token)
        print("Livekit token",token, "Livekit JWT", token.to_jwt())

        return token.to_jwt()
    except Exception as e:
        print(e)
        
@app.route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200

def generate_guest_uid():
    return 'guest-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 4242)), debug=True)
