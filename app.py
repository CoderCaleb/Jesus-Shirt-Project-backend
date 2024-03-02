import json
from flask_cors import CORS
import stripe

stripe.api_key = 'sk_test_51OOBnGEvVCl2vla1w7zQ4XYBPSUslUZvifWMvfr2iji0OcoZQzfS39yYA6et6v9jKkb35D5040HdwHAvQ4fUfN7p005LTIQPJ5'

from flask import Flask, render_template, jsonify, request


app = Flask(__name__, static_folder='public',
            static_url_path='', template_folder='public')
CORS(app, resources={r"/*": {"origins": ["http://localhost:3000", "https://jesus-shirt-shop.netlify.app"]}})

def calculate_order_amount(items):
    # Calculate total price for items
    total_price = sum(item['price'] * item['quantity'] for item in items)
    
    # Add $2 for shipping
    total_price += 2

    return int(total_price*100)


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
        })
    except Exception as e:
        return jsonify(error=str(e)), 403
    
if __name__ == '__main__':
    app.run(port=4242)