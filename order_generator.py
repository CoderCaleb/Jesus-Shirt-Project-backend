import random
import string
import uuid
import time
import json
import secrets

first_names = ["Lucas", "Sofia", "James", "Emma", "Noah", "Ava", "Liam", "Mia"]
last_names = ["Meyer", "Ramirez", "Walker", "Tanaka", "Kumar", "Smith", "Garcia"]

cities = [
    ("Berlin", "DE", "10115", "Berlin"),
    ("Madrid", "ES", "28001", "Madrid"),
    ("Sydney", "AU", "2000", "NSW"),
    ("Toronto", "CA", "M5V", "Ontario"),
    ("Singapore", "SG", "238801", ""),
    ("Tokyo", "JP", "100-0001", "Tokyo")
]

statuses = ["processing", "printing", "shipped"]

sizes = ["S", "M", "L", "XL"]

product_ids = ["1", "2", "3", "4", "5"]


def generate_order_number():
    number = random.randint(10000, 99999)
    suffix = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=4))
    return f"ORD{number}{suffix}"


def generate_order_token():
    return secrets.token_hex(32)


def generate_payment_id():
    return "pi_" + secrets.token_hex(12)


def generate_payment_method():
    return "pm_" + secrets.token_hex(12)


def random_customer():
    first = random.choice(first_names)
    last = random.choice(last_names)

    return {
        "name": f"{first} {last}",
        "emailAddress": f"{first.lower()}.{last.lower()}@example.com"
    }


def random_address():
    city, country, postal, state = random.choice(cities)

    return {
        "city": city,
        "country": country,
        "line1": f"{random.randint(1,150)} Main Street",
        "line2": None,
        "postal_code": postal,
        "state": state
    }


def random_order_items():
    item = {
        "id": random.choice(product_ids),
        "quantity": random.randint(1, 3),
        "size": random.choice(sizes)
    }

    return json.dumps([item])


def generate_order(orders_collection, linked_user=None, session=None):
    base_price = random.randint(3500, 9000)
    shipping_cost = round(random.uniform(3, 8), 2)

    latest_order_number = get_latest_order_number(orders_collection, session)

    order_number = generate_sequential_order_number(latest_order_number)

    return {
        "_id": order_number,
        "customer": random_customer(),
        "status": random.choice(statuses),
        "order_items": random_order_items(),
        "total_price": base_price,
        "payment_id": generate_payment_id(),
        "shipping_address": random_address(),
        "shipping_cost": str(shipping_cost),
        "payment_method": generate_payment_method(),
        "order_date": int(time.time()) - random.randint(0, 600),
        "linked_user": linked_user,
        "order_number": order_number,
        "order_token": generate_order_token(),
        "order_type": "tester"
    }
    
def get_latest_order_number(orders_collection, session=None):
    doc = orders_collection.find_one(
        sort=[("order_number", -1)],
        projection={"order_number": 1},
        session=session
    )

    return doc["order_number"] if doc else None   

def generate_unique_suffix(length=4):
    # Generate a unique alphanumeric suffix
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def generate_sequential_order_number(last_order_number):
    if not last_order_number:
        return "ORD00001" + generate_unique_suffix()

    numeric_part = int(last_order_number[3:8])
    next_numeric_part = numeric_part + 1

    return "ORD" + str(next_numeric_part).zfill(5) + generate_unique_suffix()