# validators.py
import re
from datetime import datetime, timezone
from dateutil import parser

def validate_email(email):
    regex = r'^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$'
    return re.match(regex, email) is not None

def validate_name(name):
    regex = r'^[a-zA-Z\s]*$'
    return name.strip() != "" and re.match(regex, name) is not None

def validate_password(password):
    regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$'
    return re.match(regex, password) is not None

def validate_birthday(birthday):
    # Parse the birthday string into a datetime object
    birthday = parser.parse(birthday)
    
    # Ensure today is timezone-aware and set to UTC
    today = datetime.now(timezone.utc)

    # Ensure birthday is timezone-aware
    if birthday.tzinfo is None:
        birthday = birthday.replace(tzinfo=timezone.utc)
        
    # Check if birthday is before January 1, 1900
    if birthday < datetime(1900, 1, 1, tzinfo=timezone.utc):
        return "Birthday cannot be before January 1, 1900"
    
    # Check if birthday is in the future
    if birthday > today:
        return "Birthday cannot be in the future"
    
    # Calculate age
    age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
    
    # Check if the user is at least 10 years old
    if age < 10:
        return "You must be at least 10 years old to sign up"
    
    return True

def validate_clothing_preference(clothing_preference):
    valid_preferences = ["Mens", "Womens", "No preference"]
    return clothing_preference in valid_preferences

def validate_fields(fields, data):
    errors = {}

    validations = {
        "email": lambda: validate_email(data.get("email")) or errors.update({"email": "Email is not valid"}),
        "name": lambda: validate_name(data.get("name")) or errors.update({"name": "Name is not valid"}),
        "password": lambda: validate_password(data.get("password")) or errors.update({
            "password": "Password needs to be at least 8 characters long and contains at least one uppercase letter, one lowercase letter, and one number."
        }),
        "birthday": lambda: validate_birthday(data.get("birthday")) or errors.update({
            "birthday": validate_birthday(data.get("birthday"))
        }),
        "clothingPreference": lambda: validate_clothing_preference(data.get("clothingPreference")) or errors.update({
            "clothingPreference": "Clothing preference needs to be either Mens, Womens, or No preference"
        }),
    }

    for field in fields:
        if field in validations:
            validations[field]()

    return errors
