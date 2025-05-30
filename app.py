from flask import Flask, render_template, request, jsonify
import requests
import json
import jwt
import time
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from html import unescape
from markupsafe import Markup

app = Flask(__name__)

class MMSAPIClient:
    def __init__(self):
        # Load credentials from environment variables (secure for production)
        self.store_code = os.environ.get('STORE_CODE')
        self.uuid = os.environ.get('API_UUID') 
        self.private_key = os.environ.get('PRIVATE_KEY')
        self.host = "https://mms-api.shoalter.com/mmsAdmin"
        
        # SKU prefix configuration
        self.sku_prefix = os.environ.get('SKU_PREFIX', 'B1112001_S_')
        
        # Fallback to credentials.json for local development
        if not all([self.store_code, self.uuid, self.private_key]):
            try:
                with open('credentials.json', 'r') as f:
                    creds = json.load(f)
                    self.store_code = creds.get('store_code')
                    self.uuid = creds.get('uuid')
                    self.private_key = creds.get('private_key')
                    self.sku_prefix = creds.get('sku_prefix', 'B1112001_S_')
            except FileNotFoundError:
                pass
        
        if not all([self.store_code, self.uuid, self.private_key]):
            raise ValueError("Missing required credentials: STORE_CODE, API_UUID, PRIVATE_KEY")
    
    def format_sku_code(self, user_input):
        """Format SKU code - add prefix if not already present"""
        user_input = user_input.strip()
        
        # If user input already contains the full SKU format, use as is
        if '_S_' in user_input:
            return user_input
        
        # Otherwise, add the prefix
        return f"{self.sku_prefix}{user_input}"
    
    def clean_and_format_html(self, html_text):
        """Clean and format HTML text while preserving essential formatting"""
        if not html_text:
            return ""
        
        # Decode HTML entities first
        clean_text = unescape(html_text)
        
        # Fix common HTML issues and normalize tags
        # Replace <br> variants with standard <br>
        clean_text = re.sub(r'<br\s*/?>', '<br>', clean_text, flags=re.IGNORECASE)
        
        # Replace <p> tags with <div> for better spacing
        clean_text = re.sub(r'<p\s*([^>]*)>', r'<div\1>', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'</p>', '</div>', clean_text, flags=re.IGNORECASE)
        
        # Ensure proper spacing around block elements
        clean_text = re.sub(r'</div>\s*<div>', '</div><br><div>', clean_text)
        
        # Clean up extra whitespace but preserve line breaks
        clean_text = re.sub(r'\n\s*\n', '\n', clean_text)
        clean_text = re.sub(r'[ \t]+', ' ', clean_text)
        
        # Remove empty tags
        clean_text = re.sub(r'<([^/>]+)>\s*</\1>', '', clean_text)
        
        return clean_text.strip()
    
    def html_to_plain_text(self, html_text):
        """Convert HTML to plain text for sharing (removing HTML tags but preserving formatting)"""
        if not html_text:
            return ""
        
        # Decode HTML entities
        clean_text = unescape(html_text)
        
        # Replace <br> with newlines
        clean_text = re.sub(r'<br\s*/?>', '\n', clean_text, flags=re.IGNORECASE)
        
        # Replace </p> and </div> with double newlines for paragraph separation
        clean_text = re.sub(r'</(?:p|div)>', '\n\n', clean_text, flags=re.IGNORECASE)
        
        # Remove all other HTML tags
        clean_text = re.sub(r'<[^>]+>', '', clean_text)
        
        # Clean up multiple newlines
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)
        
        # Remove extra whitespace
        clean_text = re.sub(r'[ \t]+', ' ', clean_text)
        clean_text = clean_text.strip()
        
        return clean_text
    
    def generate_token(self):
        """Generate JWT token for API authentication"""
        current_timestamp = int(time.time())
        
        payload = {
            "sub": "shoalter",
            "name": "shoalter", 
            "iat": current_timestamp,
            "x-api-key": self.uuid
        }
        
        # Format private key properly
        if not self.private_key.startswith('-----BEGIN'):
            formatted_key = f"-----BEGIN PRIVATE KEY-----\n{self.private_key}\n-----END PRIVATE KEY-----"
        else:
            formatted_key = self.private_key.replace('\\n', '\n')
        
        token = jwt.encode(payload, formatted_key, algorithm='RS256')
        return token
    
    def get_product(self, user_sku_input):
        """Fetch product details from MMS API using GET method"""
        try:
            # Format the SKU code
            full_sku_code = self.format_sku_code(user_sku_input)
            print(f"User input: '{user_sku_input}' -> Full SKU: '{full_sku_code}'")
            
            token = self.generate_token()
            
            headers = {
                'Content-Type': 'application/json',
                'x-auth-token': token,
                'storeCode': self.store_code,
                'platformCode': 'HKTV',
                'businessType': 'eCommerce'
            }
            
            # Use GET method with request body as per documentation
            payload = [{"skuCode": full_sku_code}]
            
            # Try the GET method first as per documentation
            response = requests.get(
                f"{self.host}/oapi/api/product/details",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            print(f"Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 'success' and data.get('data'):
                    product_data = data['data'][0]
                    return self.format_product_data(product_data, user_sku_input)
                else:
                    print(f"API returned no data: {data}")
                    return None
            elif response.status_code == 405:
                # If GET doesn't work, try POST as alternative
                print("GET method not allowed, trying POST...")
                return self.get_product_post(full_sku_code, user_sku_input)
            else:
                print(f"API Error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error fetching product: {str(e)}")
            return None
    
    def get_product_post(self, full_sku_code, user_input):
        """Alternative method using POST if GET fails"""
        try:
            token = self.generate_token()
            
            headers = {
                'Content-Type': 'application/json',
                'x-auth-token': token,
                'storeCode': self.store_code,
                'platformCode': 'HKTV',
                'businessType': 'eCommerce'
            }
            
            payload = [{"skuCode": full_sku_code}]
            
            response = requests.post(
                f"{self.host}/oapi/api/product/details",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            print(f"POST Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 'success' and data.get('data'):
                    product_data = data['data'][0]
                    return self.format_product_data(product_data, user_input)
                else:
                    print(f"POST API returned no data: {data}")
                    return None
            else:
                print(f"POST API Error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error in POST method: {str(e)}")
            return None
    
    def format_product_data(self, product_data, user_input):
        """Format product data for frontend"""
        # Get main image
        main_image = None
        if product_data.get('imagesMainPhotoList'):
            main_image = product_data['imagesMainPhotoList'][0].get('filePath')
        
        # Format price
        original_price = product_data.get('originalPrice', 0)
        selling_price = product_data.get('sellingPrice')
        currency = product_data.get('currencyCode', 'HKD')
        
        if selling_price and selling_price != original_price:
            price_text = f"{currency} ${selling_price} (原價: {currency} ${original_price})"
        else:
            price_text = f"{currency} ${original_price}"
        
        # Get brand and title
        brand = product_data.get('brandNameTc') or product_data.get('brandNameEn') or ""
        title = product_data.get('skuNameTchi') or product_data.get('skuName') or ""
        
        # Format title with brand
        if brand and title:
            formatted_title = f"{brand} | {title}"
        else:
            formatted_title = title
        
        # Get descriptions with HTML formatting preserved
        short_desc_raw = product_data.get('skuSDescCh') or product_data.get('skuSDescEn') or ""
        long_desc_raw = product_data.get('skuLDescCh') or product_data.get('skuLDescEn') or ""
        
        # Format HTML for display
        short_desc_html = self.clean_and_format_html(short_desc_raw)
        long_desc_html = self.clean_and_format_html(long_desc_raw)
        
        # Convert to plain text for sharing
        short_desc_plain = self.html_to_plain_text(short_desc_raw)
        long_desc_plain = self.html_to_plain_text(long_desc_raw)
        
        return {
            'skuCode': product_data.get('fullSkuCode'),
            'userInput': user_input,  # Store original user input
            'title': formatted_title,
            'titleEn': product_data.get('skuName'),
            'shortDescription': Markup(short_desc_html),  # HTML for display
            'longDescription': Markup(long_desc_html),   # HTML for display
            'shortDescriptionPlain': short_desc_plain,   # Plain text for sharing
            'longDescriptionPlain': long_desc_plain,     # Plain text for sharing
            'price': price_text,
            'originalPrice': original_price,
            'sellingPrice': selling_price,
            'currency': currency,
            'image': main_image,
            'brand': brand,
            'category': product_data.get('primaryCategoryCode'),
            'barcode': product_data.get('barcode')
        }

# Initialize API client
try:
    api_client = MMSAPIClient()
    print(f"API Client initialized successfully with SKU prefix: {api_client.sku_prefix}")
except ValueError as e:
    print(f"Configuration Error: {e}")
    api_client = None

@app.route('/')
def index():
    sku_prefix = api_client.sku_prefix if api_client else 'B1112001_S_'
    return render_template('index.html', sku_prefix=sku_prefix)

@app.route('/api/product', methods=['POST'])
def get_product():
    if not api_client:
        return jsonify({
            'success': False, 
            'error': '伺服器配置錯誤，請聯絡管理員'
        }), 500
    
    try:
        data = request.get_json()
        user_sku_input = data.get('skuCode', '').strip()
        
        if not user_sku_input:
            return jsonify({
                'success': False,
                'error': '請輸入產品SKU代碼'
            }), 400
        
        print(f"Searching for product with user input: {user_sku_input}")
        
        # Get product with auto-formatted SKU
        product = api_client.get_product(user_sku_input)
        
        if product:
            # Convert Markup objects to strings for JSON serialization
            product_json = dict(product)
            product_json['shortDescription'] = str(product['shortDescription'])
            product_json['longDescription'] = str(product['longDescription'])
            
            return jsonify({
                'success': True,
                'product': product_json
            })
        else:
            return jsonify({
                'success': False,
                'error': f'找不到產品代碼 "{user_sku_input}"，請檢查代碼是否正確'
            }), 404
            
    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': '系統發生錯誤，請稍後再試'
        }), 500

@app.route('/api/test', methods=['GET'])
def test_api():
    """Test endpoint to check API connectivity"""
    if not api_client:
        return jsonify({'error': 'API client not configured'}), 500
    
    try:
        token = api_client.generate_token()
        return jsonify({
            'success': True,
            'store_code': api_client.store_code,
            'sku_prefix': api_client.sku_prefix,
            'uuid': api_client.uuid[:8] + '...',  # Show only first 8 chars for security
            'token_generated': bool(token),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/product/<sku_code>')
def product_detail(sku_code):
    """Product detail page for sharing"""
    if not api_client:
        return "系統錯誤", 500
        
    product = api_client.get_product(sku_code)
    if product:
        return render_template('product_detail.html', product=product)
    else:
        return "找不到產品", 404

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat()})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))